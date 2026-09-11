extends SceneTree

var meshes: int = 0
var triangles: int = 0
var materials: int = 0
var collision_shapes: int = 0
var problems: Array[String] = []

func inspect_node(node: Node) -> void:
	if node is MeshInstance3D:
		if node.mesh == null:
			problems.append("Missing mesh: " + node.name)
		else:
			meshes += 1
			for surface in range(node.mesh.get_surface_count()):
				var indices = node.mesh.surface_get_array_index_len(surface)
				triangles += int((indices if indices > 0 else node.mesh.surface_get_array_len(surface)) / 3)
				if node.get_active_material(surface) != null:
					materials += 1
				else:
					problems.append("Missing material: " + node.name)
			node.create_convex_collision()
	if node is CollisionShape3D and node.shape != null:
		collision_shapes += 1
	for child in node.get_children():
		inspect_node(child)

func _initialize() -> void:
	var packed = load("res://asset.glb")
	if not packed is PackedScene:
		push_error("GLB did not import as PackedScene")
		quit(1)
		return
	var instance = packed.instantiate()
	root.add_child(instance)
	inspect_node(instance)
	if meshes == 0 or triangles == 0:
		problems.append("No renderable geometry")
	if collision_shapes == 0:
		problems.append("Could not create any collision shape")
	var scene = PackedScene.new()
	# Keep an imported scene instance for opening the validation scene in the editor.
	instance.owner = null
	scene.pack(instance)
	ResourceSaver.save(scene, "res://asset_test.tscn")
	var result = {"passed": problems.is_empty(), "meshes": meshes, "triangles": triangles,
		"materials": materials, "collision_shapes": collision_shapes, "errors": problems,
		"godot_version": Engine.get_version_info().string}
	var file = FileAccess.open("res://validation.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  "))
	file.close()
	print(JSON.stringify(result))
	quit(0 if problems.is_empty() else 1)
