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
    open(path, "w", encoding=encoding, newline="\r\n").write(data)

# ============================================================
# INPUT lista_konk_* parsing (tabela |...|)
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
    if re.match(r"^\d+\s*:\s*\d+", t):  # wyklucz "1:5"
        return False
    if pipes and len(line) < pipes[-1]:
        return False
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
        self.plus_positions = plus_positions[:]      # list[int]
        self.col_slices = col_slices[:]              # list[(start,end)]
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

    sep_idx = None
    for j in range(header_idx + 1, min(header_idx + 10, len(lines))):
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

    data_idx = None
    for k in range(sep_idx + 1, len(lines)):
        if re.match(r"^\s*\d+", lines[k]):
            data_idx = k
            break
    if data_idx is None:
        raise ValueError("Szablon LKON: nie znaleziono pierwszej linii danych pod tabelą.")

    line_len = len(lines[data_idx])

    col_slices = []
    for i in range(len(plus_positions) - 1):
        start = plus_positions[i] + 1
        end = plus_positions[i + 1]
        col_slices.append((start, end))

    layout = LkonLayout(plus_positions, col_slices, line_len)

    if layout.ncols != 13:
        raise ValueError(f"Szablon LKON: wykryto {layout.ncols} kolumn, a oczekiwane jest 13 (LKON_M02).")

    return layout

# ============================================================
# Helpers: metadane lotu z inputu (regexy)
# ============================================================

def _first_match(lines, pattern, flags=re.IGNORECASE):
    rx = re.compile(pattern, flags)
    for ln in lines:
        m = rx.search(ln)
        if m:
            return m
    return None

def _first_date(lines):
    # dd.mm.yyyy
    m = _first_match(lines, r"(\d{2}\.\d{2}\.\d{4})")
    return m.group(1) if m else None

def _first_time(lines):
    m = _first_match(lines, r"(\d{1,2}:\d{2}:\d{2})")
    return m.group(1) if m else None

def parse_flight_meta_from_input(lines):
    """
    Próbuje wyciągnąć metadane lotu z wejściowego pliku tekstowego.
    Jeśli czegoś nie znajdzie -> None.
    """
    meta = {}

    # data lotu
    meta["date"] = None
    m = _first_match(lines, r"Data\s+odbytego\s+lotu.*?(\d{2}\.\d{2}\.\d{4})")
    if m:
        meta["date"] = m.group(1)
    else:
        meta["date"] = _first_date(lines)

    # miejscowość (po frazie)
    meta["place"] = None
    for i, ln in enumerate(lines):
        if re.search(r"miejscowo", ln, re.IGNORECASE):
            # w LKON wzorcowym miejscowość jest w kolejnej linii
            if i + 1 < len(lines):
                cand = lines[i + 1].strip()
                # wyczyść z ozdobników
                cand = re.sub(r"[¦\|\-]+", " ", cand).strip()
                if cand:
                    meta["place"] = cand
                    break
    if not meta["place"]:
        m = _first_match(lines, r"miejscowo\S*\s*[:\-]\s*(.+)")
        if m:
            meta["place"] = m.group(1).strip()

    # oddział
    meta["oddzial"] = None
    m = _first_match(lines, r"Oddział\w*\s*[:\-]?\s*([A-ZĄĆĘŁŃÓŚŹŻ0-9 .\-]+)")
    if m:
        meta["oddzial"] = m.group(1).strip()

    # nr listy konkursowej np 02/2014
    meta["lista_no"] = None
    m = _first_match(lines, r"LISTA\s+KONKURSOWA\s+(\d{1,2}/\d{4})")
    if m:
        meta["lista_no"] = m.group(1)

    # godzina wypuszczenia
    meta["start_time"] = None
    m = _first_match(lines, r"Godzina\s+wypuszczenia.*?(\d{1,2}:\d{2}:\d{2})")
    if m:
        meta["start_time"] = m.group(1)

    # odległość do punktu średniego [m]
    meta["avg_m"] = None
    m = _first_match(lines, r"Odległość.*?-\s*([0-9 ]+)\s*\[m\]", flags=re.IGNORECASE)
    if m:
        meta["avg_m"] = re.sub(r"\s+", "", m.group(1))

    # hodowcy, gołębie, konkursy 1:4, 1:5
    def _grab_int(label_pat, key):
        mm = _first_match(lines, label_pat + r".*?-\s*([0-9 ]+)", flags=re.IGNORECASE)
        if mm:
            meta[key] = re.sub(r"\s+", "", mm.group(1))
        else:
            meta[key] = None

    _grab_int(r"Ilość\s+hodowców", "hod")
    _grab_int(r"Ilość\s+gołębi", "gol")
    _grab_int(r"Ilość\s+konkursów\s*\(baza\s*1:4\)", "k14")
    _grab_int(r"Ilość\s+konkursów\s*\(baza\s*1:5\)", "k15")

    # pierwszy/ostatni
    meta["first_time"] = None
    meta["last_time"] = None
    meta["first_speed"] = None
    meta["last_speed"] = None

    m = _first_match(lines, r"Godzina\s+przylotu\s+pierwszego.*?(\d{1,2}:\d{2}:\d{2})", flags=re.IGNORECASE)
    if m: meta["first_time"] = m.group(1)

    m = _first_match(lines, r"Prędkość\s+pierwszego.*?([0-9]+[.,][0-9]+)", flags=re.IGNORECASE)
    if m: meta["first_speed"] = m.group(1).replace(",", ".")

    m = _first_match(lines, r"Godzina\s+przylotu\s+ostatniego.*?(\d{1,2}:\d{2}:\d{2})", flags=re.IGNORECASE)
    if m: meta["last_time"] = m.group(1)

    m = _first_match(lines, r"Prędkość\s+ostatniego.*?([0-9]+[.,][0-9]+)", flags=re.IGNORECASE)
    if m: meta["last_speed"] = m.group(1).replace(",", ".")

    return meta

# ============================================================
# Nagłówek: podmiana wartości w szablonie zachowując format
# ============================================================

def _replace_after_dash(line: str, new_value: str) -> str:
    """
    Podmienia część po ostatnim '-' zachowując odstępy po lewej.
    Np: '... - 30.08.2014 rok' -> '... - <new_value>'
    """
    if new_value is None:
        return line
    m = re.match(r"^(.*?-\s*)(.*)$", line)
    if not m:
        return line
    left = m.group(1)
    # zachowaj ewentualne końcówki typu 'rok' / '[m]' jeśli są częścią formatu - ale tu dajemy już gotowe new_value
    return left + new_value

def apply_meta_to_template_lines(template_lines, meta):
    """
    template_lines: list[str] (cp1250 decoded)
    Zwraca: list[str] z podmienionym nagłówkiem (tylko tam gdzie wykryliśmy wartości).
    """
    out = template_lines[:]

    # LISTA KONKURSOWA XX/YYYY
    if meta.get("lista_no"):
        for i, ln in enumerate(out):
            if "LISTA KONKURSOWA" in ln:
                out[i] = re.sub(r"(LISTA\s+KONKURSOWA)\s+.*", r"\1 " + meta["lista_no"], ln, flags=re.IGNORECASE)
                break

    # Oddziału ...
    if meta.get("oddzial"):
        for i, ln in enumerate(out):
            if re.search(r"Oddziału", ln, re.IGNORECASE):
                # zachowaj prefiks i spacje: podmień tylko końcówkę
                out[i] = re.sub(r"(Oddziału\s+)(.+)$", r"\1" + meta["oddzial"], ln, flags=re.IGNORECASE)
                break

    # miejscowość: linia po "odbytego z miejscowości"
    if meta.get("place"):
        for i, ln in enumerate(out):
            if re.search(r"odbytego\s+z\s+miejscowości", ln, re.IGNORECASE):
                if i + 2 < len(out):
                    # w wzorcu miejscowość jest w następnej "drukowanej" linii
                    out[i + 2] = out[i + 2][:0] + out[i + 2].replace(out[i + 2].strip(), meta["place"])
                break

    # Data odbytego lotu - <date> rok
    if meta.get("date"):
        for i, ln in enumerate(out):
            if re.search(r"Data\s+odbytego\s+lotu", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, f"{meta['date']} rok")
                break

    # Godzina wypuszczenia - hh:mm:ss
    if meta.get("start_time"):
        for i, ln in enumerate(out):
            if re.search(r"Godzina\s+wypuszczenia", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, meta["start_time"])
                break

    # Odległość do punktu średniego oddziału - N [m]
    if meta.get("avg_m"):
        for i, ln in enumerate(out):
            if re.search(r"Odległość\s+do\s+punktu\s+średniego\s+oddziału", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, f"{meta['avg_m']} [m]")
                break

    # Ilości
    def _rep(label_pat, key):
        if meta.get(key):
            for i, ln in enumerate(out):
                if re.search(label_pat, ln, re.IGNORECASE):
                    out[i] = _replace_after_dash(ln, meta[key])
                    break

    _rep(r"Ilość\s+hodowców", "hod")
    _rep(r"Ilość\s+gołębi", "gol")
    _rep(r"Ilość\s+konkursów\s*\(baza\s*1:4\)", "k14")
    _rep(r"Ilość\s+konkursów\s*\(baza\s*1:5\)", "k15")

    # Godzina/prędkość pierwszego/ostatniego
    if meta.get("first_time"):
        for i, ln in enumerate(out):
            if re.search(r"Godzina\s+przylotu\s+pierwszego", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, meta["first_time"])
                break
    if meta.get("first_speed"):
        for i, ln in enumerate(out):
            if re.search(r"Prędkość\s+pierwszego", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, f"{meta['first_speed']} [m/min.]")
                break
    if meta.get("last_time"):
        for i, ln in enumerate(out):
            if re.search(r"Godzina\s+przylotu\s+ostatniego", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, meta["last_time"])
                break
    if meta.get("last_speed"):
        for i, ln in enumerate(out):
            if re.search(r"Prędkość\s+ostatniego", ln, re.IGNORECASE):
                out[i] = _replace_after_dash(ln, f"{meta['last_speed']} [m/min.]")
                break

    # Linia w stopce nad tabelą: "30.08.2014.-SZPROTAWA"
    if meta.get("date") or meta.get("place"):
        d = meta.get("date")
        p = meta.get("place")
        if d and p:
            token = f"{d}.-{p}"
            for i, ln in enumerate(out):
                if re.search(r"\d{2}\.\d{2}\.\d{4}\.\-", ln):
                    out[i] = re.sub(r"\d{2}\.\d{2}\.\d{4}\.\-.*?(\s+\-\s*\d+\s*\-)\s*$",
                                    token + r"\1", ln)
                    # jeśli regex nie chwyci, spróbuj prościej:
                    if token not in out[i]:
                        out[i] = re.sub(r"\d{2}\.\d{2}\.\d{4}\.\-[A-ZĄĆĘŁŃÓŚŹŻ0-9 .\-]+", token, ln)
                    break

    return out

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

def km_to_int_string(x: str) -> str:
    s = (x or "").strip()
    if not s:
        return "0"
    s = s.replace(" ", "").replace(",", ".")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return "0"
    try:
        v = float(m.group(0))
        return str(int(round(v)))
    except Exception:
        return "0"

def fit_value(val: str, width: int, align: str) -> str:
    val = ensure_zero_if_blank(val)
    if len(val) > width:
        val = val[:width]
    return val.rjust(width) if align == "R" else val.ljust(width)

def force_zero_in_empty_columns(buf, layout: LkonLayout):
    for (start, end) in layout.col_slices:
        if "".join(buf[start:end]).strip() == "":
            pos = end - 1
            if start <= pos < end:
                buf[pos] = "0"

def build_lkon_row_1to1(vals, idxs, layout: LkonLayout) -> str:
    def g(k):
        idx = idxs.get(k, 0)
        return vals[idx] if idx else ""

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
    km   = km_to_int_string(g("km"))

    fields = [lp, nazw, sek, wkm, typ, obr, prz, pred, coef, pkt, sw, pkt2, km]
    aligns = ["R", "L", "R", "R", "L", "L", "R", "R", "R", "R", "R", "R", "R"]

    buf = [" "] * layout.line_len
    for col_i, (start, end) in enumerate(layout.col_slices):
        width = end - start
        s = fit_value(fields[col_i], width, aligns[col_i])
        buf[start:end] = list(s)

    # pod '+' zawsze spacje
    for p in layout.plus_positions:
        if 0 <= p < len(buf):
            buf[p] = " "

    # brak danych w kolumnie => 0
    force_zero_in_empty_columns(buf, layout)

    return "".join(buf)

# ============================================================
# B: wydruk tylko do końca PIERWSZEJ tabeli
# + z podmianą nagłówka metadanymi z inputu
# ============================================================

def build_output_only_first_table_with_meta(template_path: str, input_meta: dict,
                                            new_rows: list[str]) -> bytes:
    """
    Zwraca bytes od początku szablonu do końca pierwszej tabeli:
      - nagłówek (z uzupełnionymi danymi z inputu)
      - tabela (nowe rekordy)
      - dolna ramka tabeli (1 linia +...+)
    Nic poniżej.
    """
    tpl_lines, _ = read_text_auto(template_path)
    tpl_lines = apply_meta_to_template_lines(tpl_lines, input_meta)

    # znajdź nagłówek tabeli i rekordy w szablonie żeby wyznaczyć cięcie
    header_idx = None
    for i, ln in enumerate(tpl_lines):
        if "Lp.- NAZWISKO HODOWCY" in ln:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Szablon LKON: brak nagłówka tabeli.")

    data_start = None
    for i in range(header_idx + 1, len(tpl_lines)):
        if re.match(r"^\s*\d+", tpl_lines[i]):
            data_start = i
            break
    if data_start is None:
        raise ValueError("Szablon LKON: brak pierwszej linii danych.")

    data_end = len(tpl_lines)
    for i in range(data_start, len(tpl_lines)):
        if not re.match(r"^\s*\d+", tpl_lines[i]):
            data_end = i
            break

    footer_idx = None
    for i in range(data_end, len(tpl_lines)):
        if tpl_lines[i].strip().startswith("+") and tpl_lines[i].count("+") >= 5:
            footer_idx = i
            break

    # buduj wynik jako tekst cp1250
    out_lines = []
    out_lines.extend(tpl_lines[:data_start])
    out_lines.extend(new_rows)
    if footer_idx is not None:
        out_lines.append(tpl_lines[footer_idx])

    # UWAGA: w tej wersji świadomie nie zachowujemy surowych ESC bytes z oryginału
    # (bo podmieniamy nagłówek). W praktyce większość systemów importu tego nie potrzebuje,
    # a Ty i tak importujesz tekst. Jeśli jednak MUSISZ mieć ESC, daj znać – zrobię hybrydę.
    txt = "\r\n".join(out_lines) + "\r\n"
    return txt.encode("cp1250", errors="replace")

# ============================================================
# Conversions
# ============================================================

def convert_A_simple(input_path: str) -> str:
    # Prosty output bez kodów, same rekordy 1:1 wg LKON_TEMPLATE.TXT
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

def convert_B_printer_1to1_only_first_table_with_meta(input_path: str, template_path: str) -> str:
    layout = load_lkon_layout_from_template(template_path)

    in_lines, _ = read_text_auto(input_path)
    meta = parse_flight_meta_from_input(in_lines)

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

    new_rows = []
    for ln in in_lines[hidx + 1:]:
        if "KONIEC LISTY" in ln.upper():
            break
        if not looks_like_data_row(ln, pipes, lp_slice):
            continue
        vals = extract_fields_by_pipes(ln, pipes)
        new_rows.append(build_lkon_row_1to1(vals, idxs, layout))

    if not new_rows:
        raise ValueError("Wejście: nie znaleziono żadnych wierszy danych do konwersji.")

    out_bytes = build_output_only_first_table_with_meta(template_path, meta, new_rows)

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
        outp = convert_B_printer_1to1_only_first_table_with_meta(p, tpl)
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
        outp = convert_B_printer_1to1_only_first_table_with_meta(p, tpl)
        messagebox.showinfo("OK", f"Zapisano:\n{outp}")
    except Exception as e:
        messagebox.showerror("Błąd", str(e))

def main():
    root = tk.Tk()
    root.title("Konwerter lista_konk → LKON (1:1 LKON_M02)")
    root.geometry("760x320")
    root.resizable(False, False)

    tk.Label(
        root,
        text="Tryb B:\n"
             "- podmienia nagłówek danymi z inputu (data, miejscowość, godz. wypuszczenia itd.)\n"
             "- drukuje TYLKO pierwszą tabelę (nic poniżej)\n"
             "- ODLEGŁ. zaokrąglana do integer\n"
             "- brak danych w kolumnie => 0\n"
             "- kolumny pod '+' zawsze puste",
        justify="center"
    ).pack(pady=12)

    tk.Button(root, text="A) Prosty *_LKON.txt (same rekordy 1:1 wg LKON_TEMPLATE.TXT)", width=92, height=2, command=run_A).pack(pady=6)
    tk.Button(root, text="B1) Drukarkowy *_LKON_DRUK.txt (wybierz LKON_M02 jako szablon)", width=92, height=2, command=run_B1).pack(pady=6)
    tk.Button(root, text="B2) Drukarkowy (LKON_TEMPLATE.TXT obok EXE)", width=92, height=2, command=run_B2).pack(pady=6)

    root.mainloop()

if __name__ == "__main__":
    main()
