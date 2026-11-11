"""Mesin penerjemah.

Meniru fungsi REPLACETEXTS di Excel: daftar aturan (Text To Remove -> Text To Replace)
dijalankan BERURUTAN dari atas ke bawah dengan SUBSTITUTE (cocok sebagian kata,
peka huruf besar/kecil). Hasil satu aturan menjadi masukan aturan berikutnya.
"""


def apply_rules(text: str, rules) -> str:
    for remove, replace in rules:
        if remove:
            text = text.replace(remove, replace)
    return text


def translate_text(source: str, rules) -> str:
    rules = list(rules)
    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(apply_rules(line, rules) if line.strip() else line for line in lines)
