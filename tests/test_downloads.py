from src.downloads import download_link


def test_download_link_is_markdown_data_url():
    link = download_link("Export", "a,b\n1,2\n", "report.csv", "text/csv")
    assert "data:text/csv;base64," in link
    assert "[Export — report.csv]" in link
    assert "YSxiCjEsMgo=" in link
