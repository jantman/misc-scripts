"""
Script to generate PDFs for numerically sequenced Code128 barcode labels on
Avery 5160 / 18260 label sheets.

When printing, force rasterization and fit to full page.

Tested with Python 3.10.5 and the following dependencies:

autopep8==1.7.0
Pillow==9.2.0
pycodestyle==2.9.1
reportlab==3.6.11
toml==0.10.2

"""
import sys
import argparse
from typing import Tuple, Optional

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch, mm
from reportlab.graphics.barcode import code128


class Avery5160Code128Numeric():

    def __init__(
            self, output_filename: str, padlen: int = 6,
            prefix: Optional[str] = None
    ):
        self.output_filename: str = output_filename
        self.padlen: int = padlen
        self.prefix: Optional[str] = prefix
        self.canv: canvas.Canvas = canvas.Canvas(self.output_filename, pagesize=LETTER)
        self.canv.setPageCompression(0)
        self.bottom_margin: float = 0.5 * inch
        self.left_margin: float = (3/16) * inch
        self.row_spacing: float = 0.0
        self.col_spacing: float = (1/8) * inch
        self.cell_height: float = 1 * inch
        self.cell_width: float = (2 + (5/8)) * inch
        self.num_cols: int = 3
        self.num_rows: int = 10

    def _xy_for_cell(self, colnum: int, rownum: int) -> Tuple[float, float]:
        """
        Given a cell number, return the (x, y) coords for its bottom left corner

        :param rownum: zero-base row number, left to right
        :param colnum: zero-base colnum number, top down. NOTE this is the opposite of reportlab PDF coordinates, which have zero on the bottom of the page.
        """
        x: float = self.left_margin + (rownum * (self.cell_width + self.col_spacing))
        y: float = self.bottom_margin + ((self.num_rows - (colnum + 1)) * (self.cell_height + self.row_spacing))
        return x, y

    def _generate_cell(self, col: int, row: int, value: int):
        s: str = f'{value:0{self.padlen}}'
        if self.prefix is not None:
            s = f'{self.prefix}{value:0{self.padlen}}'
        x: float
        y: float
        x, y = self._xy_for_cell(row, col)
        # temporary outline for label cell, for testing
        # self.canv.rect(x, y, self.cell_width, self.cell_height, stroke=1, fill=0)
        self.canv.drawCentredString(
            x + (self.cell_width / 2),
            y + (0.20 * inch),
            s
        )
        barcode = code128.Code128(s, barHeight=10*mm, barWidth=1)
        barcode.drawOn(
            self.canv,
            x + ((self.cell_width - barcode.width) / 2),
            y + 34
        )

    def run(self, start_num: int, num_pages: int):
        count: int = start_num
        for pagenum in range(0, num_pages):
            for colnum in range(0, 3):
                for rownum in range(0, 10):
                    self._generate_cell(colnum, rownum, count)
                    count += 1
            self.canv.showPage()
        self.canv.save()


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description='Script to generate PDFs for numerically sequenced Code128 '
                    'barcode labels on Avery 5160 / 18260 label sheets.'
    )
    p.add_argument(
        '-p', '--pad-length', action='store', type=int, dest='padlen',
        default=6, help='Padding length for barcode; default: 6'
    )
    p.add_argument(
        '-P', '--prefix', action='store', type=str, dest='prefix',
        default=None, help='Prefix to add to barcodes; default None'
    )
    p.add_argument(
        'START_NUMBER', action='store', type=int,
        help='Starting number for first barcode label'
    )
    p.add_argument(
        'NUM_PAGES', action='store', type=int,
        help='Number of pages of barcodes to generate'
    )
    args = p.parse_args(sys.argv[1:])
    Avery5160Code128Numeric(
        'labels.pdf', padlen=args.padlen, prefix=args.prefix
    ).run(
        start_num=args.START_NUMBER, num_pages=args.NUM_PAGES
    )
