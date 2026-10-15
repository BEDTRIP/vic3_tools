from vic3tools.gui import tree

SRC = """\
types T {
\ttype my_header = base_props {
\t\tblock "text" {
\t\t\traw_text = "X"
\t\t}
\t\ttextbox = {
\t\t\tusing = fontsize_large
\t\t\tsize = { 100% 40 }
\t\t\tcolor = hsv { 0.1 0.2 0.3 }
\t\t}
\t}
}
template fontsize_large {
\tfontsize = 20
}
"""


def test_heads_values_and_lines():
    nodes = tree.parse_text(SRC)
    t = tree.find_def(nodes, "type", "my_header")
    assert (t.value, t.line, t.end_line) == ("base_props", 2, 11)
    block, box = t.children
    assert (block.head, block.name) == (["block", '"text"'], "text")
    assert [c.key for c in box.children] == ["using", "size", "color"]
    size = box.children[1]
    assert size.is_list and size.scalar() == "{ 100% 40 }"
    assert box.children[2].value == "hsv" and box.children[2].is_block
    tpl = tree.find_def(nodes, "template", "fontsize_large")
    assert tpl.props("fontsize")[0].value == "20"


def test_node_at_and_label():
    nodes = tree.parse_text(SRC)
    chain = tree.node_at(nodes, 8)
    assert [n.key for n in chain] == ["types", "type", "textbox", "size"]
    assert tree.node_at(nodes, 4)[-1].children[0].label() == ""
    assert tree.parse_text('w = { name = "abc" }')[0].label() == "abc"
