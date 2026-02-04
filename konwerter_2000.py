import os
import re
import json
import tkinter as tk
from tkinter import filedialog, messagebox

APP_NAME = "Konwerter LKON"
SETTINGS_FILE = "konwerter_lkon_settings.json"

# -------------------------
# Helpers: headers + parsing
# -------------------------
def normalize_header(s: str) -> str:
    s = (s or "").strip().upper()
    s = s.replace("\u00A0", " ")  # NBSP
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s)
    return s

def find_header_line(lines):
    for i, ln in enumerate(lines):
        if "|Lp." in ln and "Nazwa" in ln:
            return i, ln
    return None, None

def parse_pipe_header(header_line: str):
    pipes = [m.start() for m in re.finditer(r"\|", header_line)]
    if len(pipes) < 2:
        raise ValueError("Nagłówek nie ma wystarczająco znaków '|'")
    headers = []
    for c in range(len(pipes) - 1):
        s = pipes[c] + 1
        e = pipes[c + 1]
        headers.append(normalize_header(header_line[s:e]))
    return pipes, headers  # pipes: 0-based positions of '|'

def find_col(headers, synonyms):
    syns = {normalize_header(x) for x in synonyms}
    for idx, h in enumerate(headers, start=1):  # 1..n
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

def looks_like_data_row(line: str) -> bool:
    t = line.lstrip()
    return bool(t) and t[0].isdigit()

def padl(s: str, w: int) -> str:
    s = "" if s is None else str(s)
    return s[-w:].rjust(w)

def padr(s: str, w: int) -> str:
    s = "" if s is None else str(s)
    return s[:w].ljust(w)

# -------------------------
# Output builders
# -------------------------
def build_lkon_like_A(lp, nazw, sek, wkm, typ, obr, godz, predk, coef, gmp, oddz, km):
    # Prosty LKON-like (wersja A)
    return (
        f"{padl(lp,4)} "
        f"{padr(nazw,26)} "
        f"{padl(sek,2)} "
        f"{padr(wkm,8)} "
        f"{padr(typ,3)} "
        f"{padr(obr,18)} "
        f"{padr(godz,10)} "
        f"{padl(predk,9)} "
        f"{padl(coef,7)} "
        f"{padl(gmp,7)} "
        f"{padl(oddz,8)} "
        f"{padl(km,6)}"
    )

def build_lkon_like_B(lp, nazw, sek, wkm, typ, obr, godz, predk, coef, gmp, oddz, km):
    """
    Wersja B: linia danych dopasowana bardziej do "LKON drukarkowego".
    W LKON (stare raporty) linie danych często wyglądają mniej więcej tak:
        "    1 NAZWISKO ... 2 31-21-5 S PL-... 11:58:17  1458.01   0.39 100.00  20.00  20.00  143298"
    Tu robimy stałe szerokości "drukarkowe".
    """
    pkt_sw = oddz  # jeśli nie masz osobnej kolumny, duplikujemy

    return (
        f"{padl(lp,5)} "
        f"{padr(nazw,24)}"
        f"{padl(sek,1)}  "
        f"{padr(wkm,9)}"
        f"{padr(typ,1)} "
        f"{padr(obr,16)}"
        f"{padr(godz,10)}"
        f"{padl(predk,10)}"
        f"{padl(coef,5)}"
        f"{padl(gmp,9)}"
        f"{padl(pkt_sw,8)}"
        f"{padl(oddz,7)}"
        f"{padl(km,6)}"
    )

# -------------------------
# Reading input (text)
# -------------------------
def read_text_lines_guess_encoding(path: str):
    # Najczęściej cp1250 dla PL; fallback utf-8
    try:
        text = open(path, "r", encoding="cp1250", errors="strict").read()
        enc = "cp1250"
    except Exception:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
        enc = "utf-8"
    return text.splitlines(), enc

def build_result_lines_from_lista_konk(in_path: str, builder_fn):
    lines, enc = read_text_lines_guess_encoding(in_path)
    header_idx, header_line = find_header_line(lines)
    if header_idx is None:
        raise ValueError("Nie znaleziono nagłówka tabeli: linia z '|Lp.' i 'Nazwa'.")

    pipes, headers = parse_pipe_header(header_line)

    idx_lp   = find_col(headers, ["LP", "LP."])
    idx_naz  = find_col(headers, ["NAZWA", "NAZWISKO HODOWCY", "NAZWISKO", "NAZWISKO I IMI"])
    idx_s    = find_col(headers, ["S", "S."])
    idx_wkm  = find_col(headers, ["W/K/M", "W-K-M", "W K M", "WKM"])
    idx_t    = find_col(headers, ["T", "TYP"])
    idx_obr  = find_col(headers, ["NUMER OBR", "NUMER OBR.", "NR OBR", "OBRACZKA", "OBRĄCZKA"])
    idx_godz = find_col(headers, ["GODZINA", "PRZYL", "T PRZYL", "T PRZYL.", "PRZYL."])
    idx_mmin = find_col(headers, ["M/MIN", "M/MIN.", "PREDK", "PREDK.", "PREDKOSC", "PRĘDKOŚĆ"])
    idx_coef = find_col(headers, ["COEF", "COEF.", "COEFIC", "COEFIC."])
    idx_gmp  = find_col(headers, ["GMP", "PKT GMP", "PKT_GMP", "PKT"])
    idx_oddz = find_col(headers, ["ODDZ", "PKT ODDZ", "PKT_ODDZ", "PUNKTY"])
    idx_km   = find_col(headers, ["KM", "ODLEG", "ODLEG.", "ODLEGŁOŚĆ"])

    out = []
    # (Wersja A ma własny nagłówek; B nie musi — bo szablon go ma)
    for ln in lines[header_idx+1:]:
        if "KONIEC LISTY" in ln.upper():
            break
        if not looks_like_data_row(ln):
            continue
        vals = extract_fields_by_pipes(ln, pipes)
        out.append(builder_fn(
            vals[idx_lp] if idx_lp else "",
            vals[idx_naz] if idx_naz else "",
            vals[idx_s] if idx_s else "",
            vals[idx_wkm] if idx_wkm else "",
            vals[idx_t] if idx_t else "",
            vals[idx_obr] if idx_obr else "",
            vals[idx_godz] if idx_godz else "",
            vals[idx_mmin] if idx_mmin else "",
            vals[idx_coef] if idx_coef else "",
            vals[idx_gmp] if idx_gmp else "",
            vals[idx_oddz] if idx_oddz else "",
            vals[idx_km] if idx_km else "",
        ))
    if not out:
        raise ValueError("Nie znalazłem żadnych wierszy wyników do konwersji.")
    return out, enc

# -------------------------
# Version A: simple output
# -------------------------
def convert_A(in_path: str) -> str:
    result_lines, enc = build_result_lines_from_lista_konk(in_path, build_lkon_like_A)

    header = "Lp  NAZWISKO HODOWCY           s  W-K-M    T  OBRACZKA            PRZYL       PREDKOSC   COEF    PKT_GMP PKT_ODDZ ODLEG"
    sep = "-" * 120
    out_lines = [header, sep] + result_lines

    base, _ = os.path.splitext(in_path)
    out_path = base + "_LKON.txt"

    # zapis w tym samym folderze
    try:
        with open(out_path, "w", encoding=enc, newline="\r\n") as f:
            f.write("\r\n".join(out_lines) + "\r\n")
    except Exception:
        with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\r\n".join(out_lines) + "\r\n")
    return out_path

# -------------------------
# Version B: template-preserving (bytes)
# -------------------------
def find_lkon_table_block_indices(tpl_lines_bytes):
    """
    tpl_lines_bytes: list[bytes] (linie bez \r\n)
    Szukamy linii z nagłówkiem tabeli: zawiera "Lp.- NAZWISKO HODOWCY"
    Potem pierwsza linia danych: po trimie zaczyna się cyfrą.
    Zwracamy: (idx_first_data, idx_after_data) w indeksach listy.
    """
    header_idx = None
    for i, b in enumerate(tpl_lines_bytes):
        try:
            s = b.decode("cp1250", errors="ignore")
        except Exception:
            s = str(b)
        if "LP.- NAZWISKO HODOWCY" in s.upper():
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Nie znaleziono w szablonie LKON nagłówka tabeli ('Lp.- NAZWISKO HODOWCY').")

    def is_data_line(bb: bytes) -> bool:
        # ltrim + digit
        t = bb.lstrip()
        return len(t) > 0 and (48 <= t[0] <= 57)

    first_data = None
    for i in range(header_idx + 1, len(tpl_lines_bytes)):
        if is_data_line(tpl_lines_bytes[i]):
            first_data = i
            break
    if first_data is None:
        raise ValueError("Nie znaleziono w szablonie LKON pierwszej linii danych (np. '    1 ...').")

    after_data = None
    for i in range(first_data, len(tpl_lines_bytes)):
        if not is_data_line(tpl_lines_bytes[i]):
            after_data = i
            break
    if after_data is None:
        after_data = len(tpl_lines_bytes)

    return first_data, after_data

def convert_B(in_path: str, template_path: str) -> str:
    # nowe dane (tekst) -> zamieniamy na bytes cp1250 (żeby pasowało do starych LKON)
    result_lines_text, _ = build_result_lines_from_lista_konk(in_path, build_lkon_like_B)
    result_lines_bytes = [ln.encode("cp1250", errors="replace") for ln in result_lines_text]

    # szablon czytamy jako bytes, zachowując ESC i całą “drukarkę”
    tpl_bytes = open(template_path, "rb").read()
    # rozbij na linie w sposób bezpieczny
    tpl_lines = tpl_bytes.splitlines()  # usuwa \r\n / \n, zostawia treść

    first_data, after_data = find_lkon_table_block_indices(tpl_lines)

    out_lines = []
    out_lines.extend(tpl_lines[:first_data])
    out_lines.extend(result_lines_bytes)
    out_lines.extend(tpl_lines[after_data:])

    base, _ = os.path.splitext(in_path)
    out_path = base + "_LKON_DRUK.txt"

    # składamy z CRLF (jak w starych raportach)
    with open(out_path, "wb") as f:
        f.write(b"\r\n".join(out_lines) + b"\r\n")

    return out_path

# -------------------------
# Settings (remember last template)
# -------------------------
def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(d):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

# -------------------------
# GUI
# -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("520x220")
        self.resizable(False, False)

        self.settings = load_settings()

        tk.Label(
            self,
            text="Wybierz tryb konwersji.\nPlik wynikowy zapisze się w tym samym folderze co plik wejściowy.",
            justify="center"
        ).pack(pady=10)

        tk.Button(self, text="A) Prosty LKON-like (bez drukarki)",
                  width=44, height=2, command=self.run_A).pack(pady=6)

        tk.Button(self, text="B) LKON z 'drukarką' (wybierz szablon LKON_M0x)",
                  width=44, height=2, command=self.run_B_choose).pack(pady=6)

        tk.Button(self, text="B) LKON z 'drukarką' (użyj ostatniego szablonu)",
                  width=44, height=2, command=self.run_B_last).pack(pady=6)

        last = self.settings.get("last_template", "")
        self.status = tk.Label(self, text=f"Ostatni szablon: {last if last else '(brak)'}", anchor="w")
        self.status.pack(fill="x", padx=10, pady=8)

    def pick_input(self):
        return filedialog.askopenfilename(
            title="Wskaż plik lista_konk_oddz*.txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
        )

    def pick_template(self):
        return filedialog.askopenfilename(
            title="Wskaż szablon LKON (np. LKON_M01.TXT)",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
        )

    def run_A(self):
        in_path = self.pick_input()
        if not in_path:
            return
        try:
            out_path = convert_A(in_path)
            messagebox.showinfo("Gotowe", f"Zapisano:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def run_B_choose(self):
        in_path = self.pick_input()
        if not in_path:
            return
        tpl_path = self.pick_template()
        if not tpl_path:
            return
        try:
            out_path = convert_B(in_path, tpl_path)
            self.settings["last_template"] = tpl_path
            save_settings(self.settings)
            self.status.config(text=f"Ostatni szablon: {tpl_path}")
            messagebox.showinfo("Gotowe", f"Zapisano:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

    def run_B_last(self):
        in_path = self.pick_input()
        if not in_path:
            return
        tpl_path = self.settings.get("last_template", "")
        if not tpl_path or not os.path.exists(tpl_path):
            messagebox.showwarning("Brak szablonu",
                                   "Nie mam zapamiętanego szablonu.\nUżyj przycisku 'B) ... wybierz szablon'.")
            return
        try:
            out_path = convert_B(in_path, tpl_path)
            messagebox.showinfo("Gotowe", f"Zapisano:\n{out_path}")
        except Exception as e:
            messagebox.showerror("Błąd", str(e))

def main():
    App().mainloop()

if __name__ == "__main__":
    main()
