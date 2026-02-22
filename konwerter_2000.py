import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

# ============================================================
# IO + ENCODING
# ============================================================

def read_text_auto(path: str):
    try:
        txt = open(path, "r", encoding="cp1250").read()
        return txt.splitlines(), "cp1250"
    except Exception:
        txt = open(path, "r", encoding="utf-8", errors="replace").read()
        return txt.splitlines(), "utf-8"

def write_text(path: str, lines, encoding="cp1250"):
    data = "\r\n".join(lines) + "\r\n"
    try:
        open(path, "w", encoding=encoding, newline="\r\n").write(data)
    except Exception:
        open(path, "w", encoding="utf-8", newline="\r\n").write(data)

# ============================================================
# PARSING WEJŚCIA
# ============================================================

def normalize_header(s: str) -> str:
    s = s.strip().upper().replace("\u00A0", " ")
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s)
    return s

def find_input_header(lines):
    for i, ln in enumerate(lines):
        if "|Lp." in ln and "Nazwa" in ln:
            return i, ln
    return None, None

def parse_pipe_header(header_line):
    pipes = [m.start() for m in re.finditer(r"\|", header_line)]
    if len(pipes) < 2:
        raise ValueError("Nagłówek nie ma wystarczająco znaków '|'")

    headers = []
    for c in range(len(pipes) - 1):
        s = pipes[c] + 1
        e = pipes[c + 1]
        headers.append(normalize_header(header_line[s:e]))

    return pipes, headers

def find_col(headers, synonyms):
    syns = {normalize_header(x) for x in synonyms}
    for idx, h in enumerate(headers, start=1):
        if h in syns:
            return idx
    return 0

def extract_fields_by_pipes(line, pipes):
    ncols = len(pipes) - 1
    vals = [""] * (ncols + 1)
    for c in range(1, ncols + 1):
        s = pipes[c - 1] + 1
        e = pipes[c]
        chunk = line[s:e] if s < len(line) else ""
        vals[c] = chunk.strip()
    return vals

# ============================================================
# BEZPIECZNA WALIDACJA WIERSZY
# ============================================================

def is_int(s):
    return bool(re.fullmatch(r"\d+", (s or "").strip()))

def looks_like_data_row(line, pipes=None, lp_slice=None):
    t = line.strip()
    if not t:
        return False

    # wyklucz "1:5", "1:4"
    if re.match(r"^\d+\s*:\s*\d+", t):
        return False

    # sprawdź długość
    if pipes and len(line) < pipes[-1]:
        return False

    # sprawdź Lp jako integer
    if lp_slice:
        lp = line[lp_slice[0]:lp_slice[1]].strip()
        if not is_int(lp):
            return False
    else:
        first = t.split(" ", 1)[0]
        if not is_int(first):
            return False

    return True

# ============================================================
# FORMATOWANIE
# ============================================================

def padl(s, w):
    s = "" if s is None else str(s)
    return s[-w:].rjust(w)

def padr(s, w):
    s = "" if s is None else str(s)
    return s[:w].ljust(w)

# ============================================================
# WERSJA A (PROSTA)
# ============================================================

def build_lkon_A(vals, idxs):
    def g(k):
        idx = idxs.get(k, 0)
        return vals[idx] if idx else ""

    return (
        f"{padl(g('lp'),4)} "
        f"{padr(g('naz'),26)} "
        f"{padl(g('s'),2)} "
        f"{padr(g('wkm'),8)} "
        f"{padr(g('t'),3)} "
        f"{padr(g('obr'),18)} "
        f"{padr(g('godz'),10)} "
        f"{padl(g('mmin'),9)} "
        f"{padl(g('coef'),7)} "
        f"{padl(g('gmp'),7)} "
        f"{padl(g('oddz'),8)} "
        f"{padl(g('km'),6)}"
    )

def convert_A(input_path):
    lines, enc = read_text_auto(input_path)

    hidx, hline = find_input_header(lines)
    if hidx is None:
        raise ValueError("Nie znaleziono nagłówka |Lp.| + Nazwa")

    pipes, headers = parse_pipe_header(hline)

    idxs = {
        "lp":   find_col(headers, ["LP", "LP."]),
        "naz":  find_col(headers, ["NAZWA", "NAZWISKO HODOWCY", "NAZWISKO"]),
        "s":    find_col(headers, ["S"]),
        "wkm":  find_col(headers, ["W/K/M", "W-K-M", "WKM"]),
        "t":    find_col(headers, ["T"]),
        "obr":  find_col(headers, ["NUMER OBR", "OBRACZKA", "OBRĄCZKA"]),
        "godz": find_col(headers, ["GODZINA", "PRZYL"]),
        "mmin": find_col(headers, ["M/MIN", "PREDK", "PREDKOSC"]),
        "coef": find_col(headers, ["COEF"]),
        "gmp":  find_col(headers, ["GMP"]),
        "oddz": find_col(headers, ["ODDZ", "PUNKTY"]),
        "km":   find_col(headers, ["KM", "ODLEG"]),
    }

    lp_slice = None
    if idxs["lp"]:
        s = pipes[idxs["lp"] - 1] + 1
        e = pipes[idxs["lp"]]
        lp_slice = (s, e)

    out_lines = []

    for ln in lines[hidx+1:]:
        if "KONIEC LISTY" in ln.upper():
            break
        if not looks_like_data_row(ln, pipes, lp_slice):
            continue
        vals = extract_fields_by_pipes(ln, pipes)
        out_lines.append(build_lkon_A(vals, idxs))

    base, _ = os.path.splitext(input_path)
    out_path = base + "_LKON.txt"
    write_text(out_path, out_lines, enc)
    return out_path

# ============================================================
# WERSJA B (Z SZABLONEM DRUKARKI)
# ============================================================

def replace_results_in_template(template_bytes, new_lines):
    lines_b = template_bytes.splitlines(keepends=True)
    lines_t = [lb.decode("cp1250", errors="replace") for lb in lines_b]

    header_idx = None
    for i, t in enumerate(lines_t):
        if "Lp.- NAZWISKO HODOWCY" in t:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Szablon LKON: brak nagłówka tabeli")

    data_start = None
    for i in range(header_idx+1, len(lines_t)):
        if re.match(r"^\s*\d+", lines_t[i]):
            data_start = i
            break
    if data_start is None:
        raise ValueError("Szablon LKON: brak pierwszej linii danych")

    data_end = len(lines_t)
    for i in range(data_start, len(lines_t)):
        if not re.match(r"^\s*\d+", lines_t[i]):
            data_end = i
            break

    new_bytes = [(ln + "\r\n").encode("cp1250", errors="replace") for ln in new_lines]

    return b"".join(lines_b[:data_start]) + b"".join(new_bytes) + b"".join(lines_b[data_end:])

def convert_B(input_path, template_path):
    lines, _ = read_text_auto(input_path)

    hidx, hline = find_input_header(lines)
    if hidx is None:
        raise ValueError("Nie znaleziono nagłówka |Lp.| + Nazwa")

    pipes, headers = parse_pipe_header(hline)

    idxs = {
        "lp": find_col(headers, ["LP", "LP."]),
        "naz": find_col(headers, ["NAZWA", "NAZWISKO HODOWCY", "NAZWISKO"]),
        "s": find_col(headers, ["S"]),
        "wkm": find_col(headers, ["W/K/M", "W-K-M", "WKM"]),
        "t": find_col(headers, ["T"]),
        "obr": find_col(headers, ["NUMER OBR", "OBRACZKA", "OBRĄCZKA"]),
        "godz": find_col(headers, ["GODZINA", "PRZYL"]),
        "mmin": find_col(headers, ["M/MIN", "PREDK", "PREDKOSC"]),
        "coef": find_col(headers, ["COEF"]),
        "gmp": find_col(headers, ["GMP"]),
        "oddz": find_col(headers, ["ODDZ", "PUNKTY"]),
        "km": find_col(headers, ["KM", "ODLEG"]),
    }

    lp_slice = None
    if idxs["lp"]:
        s = pipes[idxs["lp"] - 1] + 1
        e = pipes[idxs["lp"]]
        lp_slice = (s, e)

    new_lines = []

    for ln in lines[hidx+1:]:
        if "KONIEC LISTY" in ln.upper():
            break
        if not looks_like_data_row(ln, pipes, lp_slice):
            continue
        vals = extract_fields_by_pipes(ln, pipes)
        new_lines.append(build_lkon_A(vals, idxs))

    tpl_bytes = open(template_path, "rb").read()
    out_bytes = replace_results_in_template(tpl_bytes, new_lines)

    base, _ = os.path.splitext(input_path)
    out_path = base + "_LKON_DRUK.txt"
    open(out_path, "wb").write(out_bytes)
    return out_path

# ============================================================
# GUI
# ============================================================

def pick_input():
    return filedialog.askopenfilename(
        title="Wskaż plik lista_konk_oddz*.txt",
        filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
    )

def pick_template():
    return filedialog.askopenfilename(
        title="Wskaż szablon LKON",
        filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
    )

def app_dir():
    return os.path.dirname(os.path.abspath(__file__))

def run_A():
    p = pick_input()
    if not p: return
    try:
        outp = convert_A(p)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def run_B1():
    p = pick_input()
    if not p: return
    tpl = pick_template()
    if not tpl: return
    try:
        outp = convert_B(p, tpl)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def run_B2():
    p = pick_input()
    if not p: return
    tpl = os.path.join(app_dir(), "LKON_TEMPLATE.TXT")
    if not os.path.exists(tpl):
        messagebox.showerror("Brak szablonu", f"Brak pliku:\n{tpl}")
        return
    try:
        outp = convert_B(p, tpl)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def main():
    root = tk.Tk()
    root.title("Konwerter lista_konk → LKON")
    root.geometry("520x220")
    root.resizable(False, False)

    tk.Label(root, text="Wybierz tryb:", font=("Arial", 12)).pack(pady=10)

    tk.Button(root, text="A) Wersja prosta (bez kodów drukarki)", width=46, height=2, command=run_A).pack(pady=6)
    tk.Button(root, text="B1) Wersja drukarkowa (wybierz szablon)", width=46, height=2, command=run_B1).pack(pady=6)
    tk.Button(root, text="B2) Wersja drukarkowa (LKON_TEMPLATE.TXT obok EXE)", width=46, height=2, command=run_B2).pack(pady=6)

    root.mainloop()

if __name__ == "__main__":
    main()
