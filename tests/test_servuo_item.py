"""servuo_item: class generator, with and without the hair-hiding variant (hooded robes)."""
import servuo_item as S


def test_plain_class_has_no_hair_logic():
    cs = S.render("Szata Testowa", "SzataTestowa", 0x537F, 22)
    assert "class SzataTestowa : BaseOuterTorso" in cs and "base(0x537F, hue)" in cs
    assert "m_Hair" not in cs and "writer.Write(0); // version" in cs


def test_hide_hair_class_hides_and_restores_and_versions():
    cs = S.render("Szata Testowa", "SzataTestowa", 0x537F, 22, hide_hair=True)
    assert "m.HairItemID = 0;" in cs and "m.HairItemID = m_HairItemID;" in cs
    assert "writer.Write(1); // version" in cs and "if (version >= 1)" in cs
    assert cs.count("{") == cs.count("}")                      # braces balanced (no template leftovers)
    assert "{{" not in cs and "{fields}" not in cs
