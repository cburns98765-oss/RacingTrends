from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter as L

N = 500                      # bet rows ready to use
URL = "https://cburns98765-oss.github.io/RacingTrends/data/sheet_cards.csv"
F = "Arial"
HDR = PatternFill("solid", fgColor="0F4D33"); HF = Font(name=F, bold=True, color="FFFFFF")
BLUE = Font(name=F, color="0000FF"); BASE = Font(name=F)
thin = Side(style="thin", color="E3DED2")

wb = Workbook()
bets = wb.active; bets.title = "Bets"
summ = wb.create_sheet("Summary"); sett = wb.create_sheet("Settings")
cards = wb.create_sheet("Cards"); lists = wb.create_sheet("Lists")

# ---------- Settings
sett["A1"] = "Settings"; sett["A1"].font = Font(name=F, bold=True, size=13)
rows = [("Stake per bet (£)", 20, "£#,##0.00", "Source: user-provided stake"),
        ("Exchange commission", 0.05, "0.0%", "Source: Betfair standard market base rate (5% of net winnings); change if yours differs")]
for i, (lab, val, fmt, note) in enumerate(rows, start=2):
    sett.cell(i, 1, lab).font = BASE
    c = sett.cell(i, 2, val); c.font = BLUE; c.number_format = fmt; c.comment = Comment(note, "Racing Trends")
sett["A5"] = "Blue cells are inputs. Every bet's stake defaults to the stake above; type over it in the Bets tab to change a single bet."
sett["A5"].font = Font(name=F, italic=True, color="66716B")
sett.column_dimensions["A"].width = 28; sett.column_dimensions["B"].width = 14

# ---------- Cards (live feed)
cards["A1"] = f'=IMPORTDATA("{URL}")'
cards["F1"] = "Runners for today and tomorrow, refreshed each morning from the Racing Trends dashboard."
cards["F1"].font = Font(name=F, italic=True, color="66716B")
cards["F5000"] = "End of feed area"            # makes the tab 5,000 rows deep so the feed has room
cards["F5000"].font = Font(name=F, color="FFFFFF")
for col, w in zip("ABCD", (12, 22, 8, 26)):
    cards.column_dimensions[col].width = w

# ---------- Lists (helpers that drive the dropdowns, one row per bet row)
lists["A1"] = '=TRANSPOSE(UNIQUE(FILTER(Cards!$A$2:$A$5000,Cards!$A$2:$A$5000<>"")))'
for i in range(2, N + 2):
    lists[f"A{i}"] = (f'=IF(Bets!$A{i}="","",IFERROR(TRANSPOSE(UNIQUE(FILTER(Cards!$B$2:$B$5000,'
                      f'Cards!$A$2:$A$5000=Bets!$A{i}))),""))')
    lists[f"U{i}"] = (f'=IF(Bets!$B{i}="","",IFERROR(TRANSPOSE(UNIQUE(FILTER(Cards!$C$2:$C$5000,'
                      f'Cards!$A$2:$A$5000=Bets!$A{i},Cards!$B$2:$B$5000=Bets!$B{i}))),""))')
    lists[f"AO{i}"] = (f'=IF(Bets!$C{i}="","",IFERROR(TRANSPOSE(FILTER(Cards!$D$2:$D$5000,'
                       f'Cards!$A$2:$A$5000=Bets!$A{i},Cards!$B$2:$B$5000=Bets!$B{i},Cards!$C$2:$C$5000=Bets!$C{i})),""))')

lists["CJ1"] = "End of list area"             # makes the tab wide enough for 46 runners
lists[f"A{N+2}"] = "Helper lists for the dropdowns in Bets (one row per bet row). Do not edit."

# ---------- Bets
heads = ["Date", "Course", "Time", "Horse", "Back / Lay", "Price", "Stake (£)", "Horse result",
         "Bet result", "Profit / loss (£)", "Lay liability (£)", "Notes"]
widths = [12, 20, 8, 24, 11, 9, 11, 13, 11, 15, 15, 30]
for j, (h, w) in enumerate(zip(heads, widths), start=1):
    c = bets.cell(1, j, h); c.font = HF; c.fill = HDR; c.alignment = Alignment(horizontal="center", vertical="center")
    bets.column_dimensions[L(j)].width = w
bets.row_dimensions[1].height = 22
bets.freeze_panes = "A2"
for i in range(2, N + 2):
    bets[f"G{i}"] = "=Settings!$B$2"
    bets[f"I{i}"] = f'=IF(J{i}="","",IF(J{i}>0,"Win","Loss"))'
    bets[f"J{i}"] = (f'=IF(OR(E{i}="",F{i}="",H{i}=""),"",IF(E{i}="Back",'
                     f'IF(H{i}="Won",G{i}*(F{i}-1)*(1-Settings!$B$3),-G{i}),'
                     f'IF(H{i}="Lost",G{i}*(1-Settings!$B$3),-G{i}*(F{i}-1))))')
    bets[f"K{i}"] = f'=IF(AND(E{i}="Lay",F{i}<>""),G{i}*(F{i}-1),"")'
    for col in "ABCDEFGHIJKL":
        c = bets[f"{col}{i}"]; c.font = BASE; c.border = Border(bottom=thin)
    bets[f"A{i}"].number_format = "dd/mm/yyyy"; bets[f"C{i}"].number_format = "hh:mm"
    bets[f"F{i}"].number_format = "0.00"
    for col in "GJK":
        bets[f"{col}{i}"].number_format = '£#,##0.00;-£#,##0.00'
    for col in "ABCDEFHL":
        bets[f"{col}{i}"].font = BLUE     # cells you fill in
    for col in "IJ":
        bets[f"{col}{i}"].alignment = Alignment(horizontal="center")

def dv(formula, rng, strict=True):
    d = DataValidation(type="list", formula1=formula, allow_blank=True, showDropDown=False,
                       showErrorMessage=True, errorStyle="stop" if strict else "warning")
    d.add(rng); bets.add_data_validation(d)

dv("Lists!$A$1:$J$1", f"A2:A{N+1}", strict=False)
dv('"Back,Lay"', f"E2:E{N+1}")
dv('"Won,Lost"', f"H2:H{N+1}")
for i in range(2, N + 2):               # dependent dropdowns, one rule per row
    dv(f"Lists!$A${i}:$T${i}", f"B{i}", strict=False)
    dv(f"Lists!$U${i}:$AN${i}", f"C{i}", strict=False)
    dv(f"Lists!$AO${i}:$CH${i}", f"D{i}", strict=False)
green = PatternFill("solid", fgColor="E3EFE8"); red = PatternFill("solid", fgColor="F7E3DE")
bets.conditional_formatting.add(f"I2:J{N+1}", FormulaRule(formula=[f'$I2="Win"'], fill=green, font=Font(color="0F4D33", bold=True)))
bets.conditional_formatting.add(f"I2:J{N+1}", FormulaRule(formula=[f'$I2="Loss"'], fill=red, font=Font(color="B2412E", bold=True)))

# ---------- Summary
summ["A1"] = "Betting summary"; summ["A1"].font = Font(name=F, bold=True, size=13)
R = f"Bets!$I$2:$I${N+1}"; G = f"Bets!$G$2:$G${N+1}"; J = f"Bets!$J$2:$J${N+1}"; E = f"Bets!$E$2:$E${N+1}"
items = [
    ("Settled bets", f'=COUNTIF({R},"Win")+COUNTIF({R},"Loss")', "0"),
    ("Bets won", f'=COUNTIF({R},"Win")', "0"),
    ("Strike rate", "=IF(B3=0,0,B4/B3)", "0.0%"),
    ("Total staked (£)", f'=SUMIFS({G},{R},"Win")+SUMIFS({G},{R},"Loss")', '£#,##0.00'),
    ("Profit / loss (£)", f"=SUM({J})", '£#,##0.00;-£#,##0.00'),
    ("Return on stakes", "=IF(B6=0,0,B7/B6)", '0.0%;-0.0%'),
    ("Back bets profit / loss (£)", f'=SUMIFS({J},{E},"Back")', '£#,##0.00;-£#,##0.00'),
    ("Lay bets profit / loss (£)", f'=SUMIFS({J},{E},"Lay")', '£#,##0.00;-£#,##0.00'),
    ("Biggest open lay liability (£)", f"=MAX(Bets!$K$2:$K${N+1})", '£#,##0.00'),
]
for k, (lab, f, fmt) in enumerate(items, start=3):
    summ.cell(k, 1, lab).font = BASE
    c = summ.cell(k, 2, f); c.number_format = fmt; c.font = Font(name=F, bold=True)
summ["A13"] = "Lay bets: stake is the backer's stake you accept. You win the stake (less commission) if the horse loses, and pay stake x (price - 1) if it wins."
summ["A13"].font = Font(name=F, italic=True, color="66716B")
summ.column_dimensions["A"].width = 30; summ.column_dimensions["B"].width = 16

wb.save("/home/claude/out/racing_bet_tracker.xlsx")
print("ok")
