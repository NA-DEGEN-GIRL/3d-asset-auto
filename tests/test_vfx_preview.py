from html.parser import HTMLParser
from pathlib import Path


class EffectOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_effect_select = False
        self.options = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select":
            self.in_effect_select = attributes.get("id") == "effect"
        elif tag == "option" and self.in_effect_select:
            self.options.append(attributes)

    def handle_endtag(self, tag):
        if tag == "select":
            self.in_effect_select = False


def test_vfx_effect_selector_has_optional_media_modes_before_initialization():
    html = Path(__file__).resolve().parents[1] / "examples" / "vfx-web" / "index.html"
    parser = EffectOptions()
    parser.feed(html.read_text(encoding="utf-8"))

    assert [option.get("value") for option in parser.options] == ["ice", "pulse", "soul"]
    assert "disabled" in parser.options[0]
    assert "disabled" not in parser.options[1]
    assert "disabled" in parser.options[2]
