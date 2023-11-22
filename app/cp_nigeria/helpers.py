from datetime import date
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT


class ReportHandler:
    def __init__(self):
        self.doc = Document()
        self.logo_path = "static/assets/logos/cpnigeria-logo.png"

        for style in self.doc.styles:
            if style.type == 1 and style.name.startswith('Heading'):
                style.font.color.rgb = RGBColor(0, 135, 83)

    def add_heading(self, text, level=1):
        self.doc.add_heading(text, level)

    def add_paragraph(self, text=None):
        self.doc.add_paragraph(text)

    def add_image(self, path, width=Inches(6), height=Inches(4)):
        self.doc.add_picture(path, width=width, height=height)

    def save(self, response):
        self.doc.save(response)

    def create_cover_sheet(self, project):
        title = f"{project.name}: Mini-Grid Implementation Plan"
        subtitle = f"Date: {date.today().strftime('%d.%m.%Y')}"
        summary = f"{project.description}"
        try:
            # Set font "Lato" for the entire self.doc
            self.doc.styles['Normal'].font.name = 'Lato'
        except ValueError:
            # Handle the exception when "Lato" is not available and set a fallback font
            self.doc.styles['Normal'].font.name = 'Arial'

        # Add logo in the right top corner
        header = self.doc.sections[0].header
        run = header.paragraphs[0].add_run()
        run.add_picture(self.logo_path, width=Pt(70))
        header.paragraphs[0].alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

        # Add title
        title_paragraph = self.doc.add_paragraph()
        title_paragraph.paragraph_format.space_before = Inches(2.5)
        title_run = title_paragraph.add_run(title)
        title_run.font.size = Pt(20)
        title_run.font.bold = True
        title_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        # Add subtitle
        subtitle_paragraph = self.doc.add_paragraph()
        subtitle_run = subtitle_paragraph.add_run(subtitle)
        subtitle_run.font.size = Pt(14)
        subtitle_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

        # Add project summary
        subtitle_paragraph = self.doc.add_paragraph()
        subtitle_run = subtitle_paragraph.add_run(summary)
        subtitle_run.font.size = Pt(14)
        subtitle_paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY

        # Add page break
        self.doc.add_page_break()

    def create_report_content(self, project):
        # TODO implement properly
        self.doc.add_heading("Overview")
        self.doc.add_paragraph("Here we will have some data about the community")
        self.doc.add_heading("Demand estimation")
        self.doc.add_paragraph("Here there will be information about how the demand was estimated, information about"
                               "community enterprises, anchor loads, etc. ")
        self.doc.add_heading("Supply system")
        self.doc.add_paragraph("Here the optimized system will be described")
        self.doc.add_heading("Technoeconomic data")
        self.doc.add_paragraph("Here we will have information about the project costs, projected tariffs etc")
        self.doc.add_heading("Contact persons")
        self.doc.add_paragraph("Here, the community will get information about who best to approach according to their"
                               "current situation (e.g. isolated or interconnected), their DisCo according to "
                               "geographical area etc.")
