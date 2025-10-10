from flask import Blueprint, request, Response
from fpdf import FPDF
from ..auth import token_required
from datetime import datetime
import traceback

pdf_bp = Blueprint('pdf_generator', __name__)

class PDF(FPDF):
    def header(self):
        try:
            self.image('app/static/assets/ecom-logo.png', 10, 8, 10)
        except FileNotFoundError:
            self.set_font('Helvetica', 'B', 16); self.cell(0, 10, 'Ecom Central', 0, 1, 'L')
        self.set_font('Helvetica', 'B', 20); self.set_text_color(34, 44, 67); self.cell(0, 10, 'Ad Set Performance Report', 0, 1, 'C')
        self.set_font('Helvetica', '', 10); self.set_text_color(128, 128, 128); self.cell(0, 10, f'Generated on: {datetime.now().strftime("%B %d, %Y")}', 0, 1, 'C')
        self.set_draw_color(220, 220, 220); self.line(10, 35, 200, 35); self.ln(10)

    def footer(self):
        self.set_y(-15); self.set_font('Helvetica', 'I', 8); self.set_text_color(128, 128, 128); self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def create_summary(self, adset_data, since, until):
        total_spend = sum(adset.get('spend', 0) for adset in adset_data)
        total_orders = sum(adset.get('totalOrders', 0) for adset in adset_data)
        total_revenue = sum(adset.get('revenue', 0) for adset in adset_data)
        overall_roas = (total_revenue / total_spend) if total_spend > 0 else 0
        overall_cpo = (total_spend / total_orders) if total_orders > 0 else 0
        self.set_font('Helvetica', 'B', 12); self.cell(0, 10, 'Report Summary', 0, 1)
        self.set_font('Helvetica', '', 10); self.cell(0, 6, f'Date Range: {since} to {until}', 0, 1); self.ln(5)
        self.set_fill_color(245, 247, 250); self.rect(10, self.get_y(), 190, 28, 'F')
        self.set_font('Helvetica', '', 10); self.set_text_color(80, 80, 80)
        self.cell(47.5, 10, 'Total Spend:', 0, 0, 'C'); self.cell(47.5, 10, 'Total Orders:', 0, 0, 'C')
        self.cell(47.5, 10, 'Overall CPO:', 0, 0, 'C'); self.cell(47.5, 10, 'Overall ROAS:', 0, 1, 'C')
        self.set_font('Helvetica', 'B', 12); self.set_text_color(0, 0, 0)
        self.cell(47.5, 6, f'Rs {total_spend:,.2f}', 0, 0, 'C'); self.cell(47.5, 6, f'{total_orders}', 0, 0, 'C')
        self.cell(47.5, 6, f'Rs {overall_cpo:,.2f}', 0, 0, 'C'); self.cell(47.5, 6, f'{overall_roas:.2f}x', 0, 1, 'C')
        self.ln(10)

    def create_table(self, adset_data):
        col_widths = [50, 18, 12, 15, 10, 15, 15, 15, 12, 12, 15]
        headers = ["Ad Set / Source", "Spend", "Orders", "Delivered", "RTO", "Cancelled", "In-Transit", "Processing", "RTO%", "CPO", "ROAS"]
        
        self.set_font('Helvetica', 'B', 8)
        self.set_fill_color(67, 56, 202); self.set_text_color(255, 255, 255)
        for i, header in enumerate(headers):
            self.cell(col_widths[i], 10, header, 1, 0, 'C', fill=True)
        self.ln()

        # --- THIS IS THE FIX ---
        # Reset the text color to black before drawing the table body
        self.set_text_color(0, 0, 0)
        # --- END OF FIX ---

        grand_totals = {key: 0 for key in ["spend", "totalOrders", "deliveredOrders", "rtoOrders", "cancelledOrders", "inTransitOrders", "processingOrders", "revenue"]}
        fill = False
        for adset in adset_data:
            for key in grand_totals: grand_totals[key] += adset.get(key, 0)
            self.set_font('Helvetica', 'B', 8)
            self.draw_row(adset, col_widths, fill=fill)
            if adset.get('id') == 'unattributed':
                self.set_font('Helvetica', '', 7)
                for term in adset.get('terms', []):
                    self.draw_row(term, col_widths, fill=fill, indent=True)
            fill = not fill

        self.set_font('Helvetica', 'B', 9)
        self.draw_row(grand_totals, col_widths, fill=True, is_total=True)

    def draw_row(self, data, widths, fill, is_total=False, indent=False):
        total_orders = data.get('totalOrders', 0); spend = data.get('spend', 0); revenue = data.get('revenue', 0)
        rto_rate = (data.get('rtoOrders', 0) / total_orders) if total_orders > 0 else 0
        cpo = (spend / total_orders) if total_orders > 0 else 0
        roas = (revenue / spend) if spend > 0 else 0

        self.set_fill_color(243, 244, 246)
        if is_total: self.set_fill_color(220, 220, 220)

        name = sanitize_string(data.get('name', 'N/A'))
        if is_total: name = "GRAND TOTAL"
        if indent: name = f"    - {name}"
        
        self.cell(widths[0], 10, name, 1, 0, 'L' if indent or not is_total else 'C', fill=fill)
        self.cell(widths[1], 10, f"{spend:,.0f}", 1, 0, 'R', fill=fill)
        self.cell(widths[2], 10, str(total_orders), 1, 0, 'C', fill=fill)
        self.cell(widths[3], 10, str(data.get('deliveredOrders', 0)), 1, 0, 'C', fill=fill)
        self.cell(widths[4], 10, str(data.get('rtoOrders', 0)), 1, 0, 'C', fill=fill)
        self.cell(widths[5], 10, str(data.get('cancelledOrders', 0)), 1, 0, 'C', fill=fill)
        self.cell(widths[6], 10, str(data.get('inTransitOrders', 0)), 1, 0, 'C', fill=fill)
        self.cell(widths[7], 10, str(data.get('processingOrders', 0)), 1, 0, 'C', fill=fill)
        self.cell(widths[8], 10, f"{rto_rate:.1%}", 1, 0, 'C', fill=fill)
        self.cell(widths[9], 10, f"{cpo:,.0f}", 1, 0, 'R', fill=fill)
        
        if not is_total:
            if roas >= 2.0: self.set_text_color(0, 128, 0)
            elif roas < 1.0: self.set_text_color(255, 0, 0)
        
        self.cell(widths[10], 10, f"{roas:.2f}x", 1, 1, 'C', fill=fill)
        self.set_text_color(0, 0, 0)

def sanitize_string(text):
    return str(text).encode('latin-1', 'replace').decode('latin-1')

@pdf_bp.route('/download-dashboard-pdf', methods=['POST'])
@token_required
def download_dashboard_pdf():
    since, until, adset_data = request.args.get('since'), request.args.get('until'), request.get_json()
    if not adset_data: return "No data provided", 400
    try:
        pdf = PDF()
        pdf.add_page(); pdf.create_summary(adset_data, since, until); pdf.create_table(adset_data)
        pdf_output_bytes = pdf.output(dest='S').encode('latin-1')
        return Response(pdf_output_bytes, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename=adset_report_{since}_to_{until}.pdf'})
    except Exception:
        print(f"--- [CRITICAL PDF ERROR] ---"); traceback.print_exc()
        return "An error occurred during PDF generation.", 500