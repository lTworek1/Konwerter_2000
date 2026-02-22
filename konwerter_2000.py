import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

# ============================================================
# IO + ENCODING
# ============================================================

def read_text_auto(path: str):
    # LKON-y zwykle cp1250
    try:
        txt = open(path, "r", encoding="cp1250").read()
        return txt.splitlines(), "cp1250"
    except Exception:
        txt = open(path, "r", encoding="utf-8", errors="replace").read()
        return txt.splitlines(), "utf-8"

def write_text(path: str, lines, encoding="cp1250"):
    data = "\r\n".join(lines) + "\r\n"
    open(path, "w", encoding=encoding, newline="\r\n").write(data)

# ============================================================
# INPUT lista_konk_* parsing (nagłówek z |...|)
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

def parse_pipe_header(header_line: str):
    pipes = [m.start() for m in re.finditer(r"\|", header_line)]
    if len(pipes) < 2:
        raise ValueError("Nagłówek wejścia nie ma wystarczająco znaków '|'")
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

def extract_fields_by_pipes(line: str, pipes):
    ncols = len(pipes) - 1
    vals = [""] * (ncols + 1)  # index 0 unused
    for c in range(1, ncols + 1):
        s = pipes[c - 1] + 1
        e = pipes[c]
        chunk = line[s:e] if s < len(line) else ""
        vals[c] = chunk.strip()
    return vals

def is_int(s: str) -> bool:
    return bool(re.fullmatch(r"\d+", (s or "").strip()))

def looks_like_data_row(line: str, pipes=None, lp_slice=None) -> bool:
    t = line.strip()
    if not t:
        return False
    # wyklucz "1:5", "1:4" itd.
    if re.match(r"^\d+\s*:\s*\d+", t):
        return False
    # linia musi mieć sensowną długość
    if pipes and len(line) < pipes[-1]:
        return False
    # Lp musi być integer
    if lp_slice:
        lp = line[lp_slice[0]:lp_slice[1]].strip()
        if not is_int(lp):
            return False
    else:
        first = t.split(" ", 1)[0]
        if not is_int(first):
            return False
    return True

def build_input_index_map(headers):
    return {
        "lp":   find_col(headers, ["LP", "LP."]),
        "naz":  find_col(headers, ["NAZWA", "NAZWISKO HODOWCY", "NAZWISKO", "NAZWISKO I IMI"]),
        "s":    find_col(headers, ["S", "S."]),
        "wkm":  find_col(headers, ["W/K/M", "W-K-M", "W K M", "WKM"]),
        "t":    find_col(headers, ["T", "TYP"]),
        "obr":  find_col(headers, ["NUMER OBR", "NUMER OBR.", "NR OBR", "OBRACZKA", "OBRĄCZKA"]),
        "godz": find_col(headers, ["GODZINA", "PRZYL", "T PRZYL", "T PRZYL.", "PRZYL."]),
        "mmin": find_col(headers, ["M/MIN", "M/MIN.", "PREDK", "PREDK.", "PREDKOSC", "PRĘDKOŚĆ"]),
        "coef": find_col(headers, ["COEF", "COEF.", "COEFIC", "COEFIC."]),
        "gmp":  find_col(headers, ["GMP", "PKT GMP", "PKT_GMP", "PKT"]),
        "oddz": find_col(headers, ["ODDZ", "PKT ODDZ", "PKT_ODDZ", "PUNKTY"]),
        "km":   find_col(headers, ["KM", "ODLEG", "ODLEG.", "ODLEGŁOŚĆ"]),
    }

# ============================================================
# TEMPLATE LKON: layout z linii "+....+"
# ============================================================

class LkonLayout:
    def __init__(self, plus_positions, col_slices, line_len):
        self.plus_positions = plus_positions[:]      # list[int] indeksy '+'
        self.col_slices = col_slices[:]              # list[(start,end)] w tej samej linii
        self.line_len = int(line_len)
        self.ncols = len(self.col_slices)

def load_lkon_layout_from_template(template_path: str) -> LkonLayout:
    lines, _ = read_text_auto(template_path)

    header_idx = None
    for i, ln in enumerate(lines):
        if "Lp.- NAZWISKO HODOWCY" in ln:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Szablon LKON: nie znaleziono nagłówka tabeli ('Lp.- NAZWISKO HODOWCY').")

    # separator z + pod nagłówkiem
    sep_idx = None
    for j in range(header_idx + 1, min(header_idx + 8, len(lines))):
        ln = lines[j]
        if ln.strip().startswith("+") and ln.count("+") >= 5:
            sep_idx = j
            break
    if sep_idx is None:
        raise ValueError("Szablon LKON: nie znaleziono separatora tabeli z '+...+' pod nagłówkiem.")

    sep_line = lines[sep_idx]
    plus_positions = [m.start() for m in re.finditer(r"\+", sep_line)]
    if len(plus_positions) < 2:
        raise ValueError("Szablon LKON: separator ma za mało '+'.")

    # długość linii danych bierzemy z pierwszego rekordu po separatorze (żeby 1:1 było jak rekord)
    data_idx = None
    for k in range(sep_idx + 1, len(lines)):
        if re.match(r"^\s*\d+", lines[k]):
            data_idx = k
            break
    if data_idx is None:
        raise ValueError("Szablon LKON: nie znaleziono pierwszej linii danych pod tabelą.")

    line_len = len(lines[data_idx])

    # slices między + (UWAGA: pozycje + mają być puste, więc dane są między nimi)
    col_slices = []
    for i in range(len(plus_positions) - 1):
        start = plus_positions[i] + 1
        end = plus_positions[i + 1]  # end exclusive
        col_slices.append((start, end))

    layout = LkonLayout(plus_positions, col_slices, line_len)

    # Dla Twojego LKON_M02 oczekujemy 13 kolumn w tabeli
    if layout.ncols != 13:
        raise ValueError(
            f"Szablon LKON: wykryto {layout.ncols} kolumn, a oczekiwane jest 13 (LKON_M02). "
            "Upewnij się, że LKON_TEMPLATE.TXT to właściwy wzór."
        )

    return layout

# ============================================================
# 1:1 row builder (puste pod '+', ucinanie, brak -> 0)
# ============================================================

def clean_time(t: str) -> str:
    t = (t or "").strip()
    if t.startswith("1-"):
        t = t[2:]
    return t

def ensure_zero_if_blank(x: str) -> str:
    x = (x or "").strip()
    return x if x else "0"

def fit_value(val: str, width: int, align: str) -> str:
    # Wymóg użytkownika: jeśli brak danych w kolumnie => "0"
    val = ensure_zero_if_blank(val)
    # twarde ucięcie
    if len(val) > width:
        val = val[:width]
    # align
    if align == "R":
        return val.rjust(width)
    return val.ljust(width)

def build_lkon_row_1to1(vals, idxs, layout: LkonLayout) -> str:
    def g(k):
        idx = idxs.get(k, 0)
        return vals[idx] if idx else ""

    # Mapowanie do 13 kolumn LKON_M02:
    # 0 Lp
    # 1 Nazwisko
    # 2 s
    # 3 W-K-S-S / WKM
    # 4 T
    # 5 Obrączka
    # 6 T PRZYL
    # 7 PRĘDKOŚĆ
    # 8 COEFIC
    # 9 PKT
    #10 SW-PUNKTY
    #11 PKT-2
    #12 ODLEG

    lp   = g("lp")
    nazw = g("naz")
    sek  = g("s")
    wkm  = g("wkm")
    typ  = g("t")
    obr  = g("obr")
    prz  = clean_time(g("godz"))
    pred = g("mmin")
    coef = g("coef")
    pkt  = g("gmp")
    sw   = g("oddz")
    pkt2 = sw
    km   = g("km")

    fields = [lp, nazw, sek, wkm, typ, obr, prz, pred, coef, pkt, sw, pkt2, km]

    # Align wg wyglądu tabeli LKON: liczby na prawo, teksty na lewo
    aligns = ["R", "L", "R", "R", "L", "L", "R", "R", "R", "R", "R", "R", "R"]

    # buduj bufor
    buf = [" "] * layout.line_len

    for col_i, (start, end) in enumerate(layout.col_slices):
        width = end - start
        s = fit_value(fields[col_i], width, aligns[col_i])
        buf[start:end] = list(s)

    # Wymóg: miejsca dokładnie pod '+' MUSZĄ być puste
    for p in layout.plus_positions:
        if 0 <= p < len(buf):
            buf[p] = " "

    return "".join(buf)

# ============================================================
# Replace block in LKON (zachowuje ESC / kody drukarki)
# ============================================================

def replace_results_in_template(template_bytes: bytes, new_lines: list[str], encoding="cp1250") -> bytes:
    lines_b = template_bytes.splitlines(keepends=True)
    lines_t = [lb.decode(encoding, errors="replace") for lb in lines_b]

    header_idx = None
    for i, t in enumerate(lines_t):
        if "Lp.- NAZWISKO HODOWCY" in t:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Szablon LKON: brak nagłówka tabeli (Lp.- NAZWISKO HODOWCY).")

    # start danych
    data_start = None
    for i in range(header_idx + 1, len(lines_t)):
        if re.match(r"^\s*\d+", lines_t[i]):
            data_start = i
            break
    if data_start is None:
        raise ValueError("Szablon LKON: brak pierwszej linii danych.")

    # koniec danych: pierwsza linia, która NIE wygląda jak rekord
    data_end = len(lines_t)
    for i in range(data_start, len(lines_t)):
        if not re.match(r"^\s*\d+", lines_t[i]):
            data_end = i
            break

    new_b = [(ln + "\r\n").encode(encoding, errors="replace") for ln in new_lines]
    return b"".join(lines_b[:data_start]) + b"".join(new_b) + b"".join(lines_b[data_end:])

# ============================================================
# Conversions
# ============================================================

def convert_A_simple(input_path: str) -> str:
    # Prosty output bez kodów drukarki, ale 1:1 wg LKON_TEMPLATE.TXT
    tpl = os.path.join(app_dir(), "LKON_TEMPLATE.TXT")
    if not os.path.exists(tpl):
        raise ValueError("Brak LKON_TEMPLATE.TXT obok programu (potrzebny do układu 1:1).")

    layout = load_lkon_layout_from_template(tpl)

    lines, enc = read_text_auto(input_path)
    hidx, hline = find_input_header(lines)
    if hidx is None:
        raise ValueError("Wejście: nie znaleziono nagłówka tabeli (|Lp.| + Nazwa).")

    pipes, headers = parse_pipe_header(hline)
    idxs = build_input_index_map(headers)

    lp_slice = None
    if idxs["lp"]:
        s = pipes[idxs["lp"] - 1] + 1
        e = pipes[idxs["lp"]]
        lp_slice = (s, e)

    out_lines = []
    for ln in lines[hidx + 1:]:
        if "KONIEC LISTY" in ln.upper():
            break
        if not looks_like_data_row(ln, pipes, lp_slice):
            continue
        vals = extract_fields_by_pipes(ln, pipes)
        out_lines.append(build_lkon_row_1to1(vals, idxs, layout))

    base, _ = os.path.splitext(input_path)
    out_path = base + "_LKON.txt"
    write_text(out_path, out_lines, encoding=enc)
    return out_path

def convert_B_printer_1to1(input_path: str, template_path: str) -> str:
    # Drukarkowy: kody + reszta z template, podmiana tylko danych
    layout = load_lkon_layout_from_template(template_path)

    in_lines, _ = read_text_auto(input_path)
    hidx, hline = find_input_header(in_lines)
    if hidx is None:
        raise ValueError("Wejście: nie znaleziono nagłówka tabeli (|Lp.| + Nazwa).")

    pipes, headers = parse_pipe_header(hline)
    idxs = build_input_index_map(headers)

    lp_slice = None
    if idxs["lp"]:
        s = pipes[idxs["lp"] - 1] + 1
        e = pipes[idxs["lp"]]
        lp_slice = (s, e)

    new_lines = []
    for ln in in_lines[hidx + 1:]:
        if "KONIEC LISTY" in ln.upper():
            break
        if not looks_like_data_row(ln, pipes, lp_slice):
            continue
        vals = extract_fields_by_pipes(ln, pipes)
        new_lines.append(build_lkon_row_1to1(vals, idxs, layout))

    if not new_lines:
        raise ValueError("Wejście: nie znaleziono żadnych wierszy danych do konwersji.")

    tpl_bytes = open(template_path, "rb").read()
    out_bytes = replace_results_in_template(tpl_bytes, new_lines, encoding="cp1250")

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
        title="Wskaż szablon LKON (np. LKON_M02.TXT)",
        filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
    )

def app_dir():
    return os.path.dirname(os.path.abspath(__file__))

def run_A():
    p = pick_input()
    if not p:
        return
    try:
        outp = convert_A_simple(p)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def run_B1():
    p = pick_input()
    if not p:
        return
    tpl = pick_template()
    if not tpl:
        return
    try:
        outp = convert_B_printer_1to1(p, tpl)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def run_B2():
    p = pick_input()
    if not p:
        return
    tpl = os.path.join(app_dir(), "LKON_TEMPLATE.TXT")
    if not os.path.exists(tpl):
        messagebox.showerror(
            "Brak szablonu",
            f"Brak pliku:\n{tpl}\n\nSkopiuj tu swój LKON_M02.TXT i nazwij LKON_TEMPLATE.TXT."
        )
        return
    try:
        outp = convert_B_printer_1to1(p, tpl)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def main():
    root = tk.Tk()
    root.title("Konwerter lista_konk → LKON (1:1 LKON_M02)")
    root.geometry("620x270")
    root.resizable(False, False)

    tk.Label(
        root,
        text="Wersja 1:1 LKON_M02:\n"
             "- kolumny wyznaczane z linii '+...+'\n"
             "- pozycje pod '+' zawsze puste\n"
             "- brak danych w kolumnie => 0\n"
             "- usuwa prefiks '1-' z T PRZYL",
        justify="center"
    ).pack(pady=12)

    tk.Button(root, text="A) Prosty *_LKON.txt (1:1 wg LKON_TEMPLATE.TXT)", width=70, height=2, command=run_A).pack(pady=6)
    tk.Button(root, text="B1) Drukarkowy *_LKON_DRUK.txt (wybierz LKON_M02 jako szablon)", width=70, height=2, command=run_B1).pack(pady=6)
    tk.Button(root, text="B2) Drukarkowy (LKON_TEMPLATE.TXT obok EXE)", width=70, height=2, command=run_B2).pack(pady=6)

    root.mainloop()

if __name__ == "__main__":
    main()
