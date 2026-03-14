from fpdf import FPDF
import re

md_path  = r"C:\claude_workspace\Skattefunn\skattefunn_soknad.md"
pdf_path = r"C:\claude_workspace\Skattefunn\skattefunn_soknad.pdf"

BLUE      = (0,   51,  102)
LIGHTBLUE = (0,   64,  128)
GREY_BG   = (244, 248, 255)
WHITE     = (255, 255, 255)
BLACK     = (17,  17,  17)

FONT_DIR = r"C:\Windows\Fonts"

class PDF(FPDF):
    def header(self):
        pass

    def setup_fonts(self):
        self.add_font("Arial", style="",  fname=FONT_DIR + r"\arial.ttf")
        self.add_font("Arial", style="B", fname=FONT_DIR + r"\arialbd.ttf")
        self.add_font("Arial", style="I", fname=FONT_DIR + r"\ariali.ttf")
        pass  # Courier not needed

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Side {self.page_no()}", align="C")

    def h1(self, text):
        self.set_font("Arial", "B", 17)
        self.set_text_color(*BLUE)
        self.ln(4)
        self.multi_cell(0, 9, text)
        self.set_draw_color(*BLUE)
        self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y()+1, self.w - self.r_margin, self.get_y()+1)
        self.ln(5)
        self.set_text_color(*BLACK)

    def h2(self, text):
        self.ln(4)
        self.set_font("Arial", "B", 13)
        self.set_text_color(*BLUE)
        self.multi_cell(0, 8, text)
        self.ln(2)
        self.set_text_color(*BLACK)

    def h3(self, text):
        self.ln(2)
        self.set_font("Arial", "B", 11)
        self.set_text_color(*LIGHTBLUE)
        self.multi_cell(0, 7, text)
        self.ln(1)
        self.set_text_color(*BLACK)

    def body(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(*BLACK)
        self.multi_cell(0, 6, text)

    def bullet(self, text):
        self.set_font("Arial", "", 10)
        self.set_text_color(*BLACK)
        x = self.get_x()
        self.set_x(self.l_margin + 4)
        self.cell(5, 6, "-")
        self.multi_cell(0, 6, text)
        self.set_x(x)

    def table_row(self, cells, header=False):
        self.set_font("Arial", "B" if header else "", 10)
        col_w = (self.w - self.l_margin - self.r_margin) / len(cells)
        if header:
            self.set_fill_color(*BLUE)
            self.set_text_color(*WHITE)
        else:
            self.set_fill_color(*GREY_BG)
            self.set_text_color(*BLACK)
        for i, cell in enumerate(cells):
            fill = header or i % 2 == 0
            self.cell(col_w, 7, cell, border=1, fill=header or False)
        self.ln()
        self.set_text_color(*BLACK)

    def separator(self):
        self.ln(2)
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def code_block(self, text):
        # Replace unicode block chars with ASCII for the Gantt chart
        text = text.replace("\u2588", "X").replace("\u2592", ".")
        self.set_font("Arial", "", 8)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 5, text, fill=True, border=1)
        self.ln(2)
        self.set_font("Arial", "", 10)
        self.set_text_color(*BLACK)


def parse_and_render(md_text, pdf):
    lines = md_text.splitlines()
    i = 0
    in_table = False
    in_code  = False
    code_buf = []
    table_rows = []

    def flush_table():
        nonlocal table_rows, in_table
        if not table_rows: return
        for ri, row in enumerate(table_rows):
            pdf.table_row(row, header=(ri == 0))
        pdf.ln(2)
        table_rows = []
        in_table = False

    while i < len(lines):
        line = lines[i]

        # Code block
        if line.strip().startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                pdf.code_block("\n".join(code_buf))
                in_code = False
                code_buf = []
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # Table
        if line.strip().startswith("|"):
            in_table = True
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            # skip separator row
            if all(set(c.replace("-","").replace(":","").strip()) == set() or c.strip().replace("-","").replace(":","") == "" for c in cols):
                i += 1
                continue
            table_rows.append(cols)
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # Headings
        if line.startswith("# "):
            pdf.h1(line[2:].strip())
        elif line.startswith("## "):
            pdf.h2(line[3:].strip())
        elif line.startswith("### "):
            pdf.h3(line[4:].strip())
        elif line.startswith("---"):
            pdf.separator()
        elif line.startswith("- ") or line.startswith("* "):
            text = line[2:].strip()
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            pdf.bullet(text)
        elif line.strip() == "":
            pdf.ln(2)
        else:
            # Strip inline bold/italic markdown
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'\1', text)
            pdf.body(text)

        i += 1

    if in_table:
        flush_table()


with open(md_path, encoding="utf-8") as f:
    md_text = f.read()

pdf = PDF(orientation="P", unit="mm", format="A4")
pdf.set_margins(25, 20, 25)
pdf.set_auto_page_break(auto=True, margin=20)
pdf.setup_fonts()
pdf.add_page()

parse_and_render(md_text, pdf)

pdf.output(pdf_path)
print(f"PDF created: {pdf_path}")
