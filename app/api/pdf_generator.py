from flask import Blueprint, request, Response
from fpdf import FPDF
from ..auth import token_required
from datetime import datetime
import traceback
import io
import os

pdf_bp = Blueprint('pdf_generator', __name__)

class PDF(FPDF):
    def header(self):
        try:
            self.image('app/static/assets/ecom-logo.png', 10, 8, 10)
        except FileNotFoundError:
            self.set_font('Helvetica', 'B', 16)
            self.cell(0, 10, 'Ecom Central', 0, 1, 'L')
        self.set_font('Helvetica', 'B', 20)
        self.set_text_color(34, 44, 67)
        self.cell(0, 10, 'Ad Set Performance Report', 0, 1, 'C')
        self.set_font('Helvetica', '', 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Generated on: {datetime.now().strftime("%B %d, %Y")}', 0, 1, 'C')
        self.set_draw_color(220, 220, 220)
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def create_summary(self, adset_data, since, until):
        total_spend = sum(adset.get('spend', 0) for adset in adset_data)
        total_orders = sum(adset.get('totalOrders', 0) for adset in adset_data)
        # Use deliveredRevenue for total revenue in summary
        total_revenue = sum(adset.get('deliveredRevenue', 0) for adset in adset_data)
        overall_roas = (total_revenue / total_spend) if total_spend > 0 else 0

        # Compute overall RTO% including cancelled
        total_delivered = sum(adset.get('deliveredOrders', 0) for adset in adset_data)
        total_rto = sum(adset.get('rtoOrders', 0) for adset in adset_data)
        total_cancelled = sum(adset.get('cancelledOrders', 0) for adset in adset_data)
        denom = total_delivered + total_rto + total_cancelled
        overall_rto_percent = ((total_rto + total_cancelled) / denom) if denom > 0 else 0

        # Header/title
        self.set_font('Helvetica', 'B', 12)
        self.cell(0, 10, 'Report Summary', 0, 1)
        self.set_font('Helvetica', '', 10)
        self.cell(0, 6, f'Date Range: {since} to {until}', 0, 1)
        self.ln(5)

        # Summary box - 4 aligned columns:
        # [Total Spend] [Total Orders] [Overall RTO%] [Overall ROAS]
        self.set_fill_color(245, 247, 250)
        box_x = 10
        box_y = self.get_y()
        box_w = 190
        box_h = 34  # enough for label row + value row
        self.rect(box_x, box_y, box_w, box_h, 'F')

        # Four equal columns
        col_w = box_w / 4.0
        label_h = 6
        value_h = 10
        padding_top = 3

        # Labels row (light gray text)
        self.set_xy(box_x, box_y + padding_top)
        self.set_font('Helvetica', '', 9)
        self.set_text_color(80, 80, 80)
        self.cell(col_w, label_h, 'Total Spend', 0, 0, 'C')
        self.cell(col_w, label_h, 'Total Orders', 0, 0, 'C')
        self.cell(col_w, label_h, 'Overall RTO%', 0, 0, 'C')
        self.cell(col_w, label_h, 'Overall ROAS', 0, 1, 'C')

        # Values row (bold, darker)
        self.set_x(box_x)
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(0, 0, 0)
        # total spend formatted with currency and no decimal places if large (consistent with table)
        self.cell(col_w, value_h, f'Rs {total_spend:,.2f}', 0, 0, 'C')
        self.cell(col_w, value_h, f'{total_orders}', 0, 0, 'C')
        self.cell(col_w, value_h, f'{overall_rto_percent:.1%}', 0, 0, 'C')
        self.cell(col_w, value_h, f'{overall_roas:.2f}x', 0, 1, 'C')

        # move below the box
        self.set_y(box_y + box_h + 6)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def create_table(self, adset_data):
        """
        Keep original design and column order except:
        - Shift deliveredRevenue to just after Spend and rename header to "Revenue"
        - Fix grand total calculation (avoid double counting unattributed terms)
        - Add a small signature block near the bottom of the page
        """
        col_widths = [50, 18, 12, 15, 10, 15, 15, 15, 12, 12, 15, 15]
        headers = ["Ad Set / Source", "Spend", "Revenue", "Orders", "Delivered", "RTO", "Cancelled", "In-Transit", "Processing", "RTO%", "CPO", "ROAS"]

        usable_width = self.w - self.l_margin - self.r_margin
        total_w = sum(col_widths)
        if total_w > usable_width:
            scale = usable_width / total_w
            col_widths = [w * scale for w in col_widths]

        rows_count = 0
        for adset in adset_data:
            rows_count += 1
            if adset.get('id') == 'unattributed':
                rows_count += len(adset.get('terms', []))
        rows_count += 1  # grand total row

        header_font_size = 8
        body_font_size = 8
        row_height = 10

        current_y = self.get_y()
        available_height = self.h - self.b_margin - current_y - 10
        required_height = (1 + rows_count) * row_height
        min_row_height = 6
        min_font_size = 6
        while required_height > available_height and row_height > min_row_height:
            row_height -= 0.5
            body_font_size = max(min_font_size, body_font_size - 0.25)
            header_font_size = max(min_font_size, header_font_size - 0.25)
            required_height = (1 + rows_count) * row_height

        self.set_font('Helvetica', 'B', int(header_font_size))
        self.set_fill_color(67, 56, 202)
        self.set_text_color(255, 255, 255)

        for i, header in enumerate(headers):
            self.cell(col_widths[i], row_height, header, 1, 0, 'C', fill=True)
        self.ln()

        self.set_text_color(0, 0, 0)
        fill = False

        grand_totals = {key: 0 for key in ["spend", "totalOrders", "deliveredOrders", "rtoOrders", "cancelledOrders", "inTransitOrders", "processingOrders", "deliveredRevenue"]}
        for adset in adset_data:
            for key in grand_totals:
                grand_totals[key] += adset.get(key, 0)

        for adset in adset_data:
            self.set_font('Helvetica', 'B', int(body_font_size))
            self.draw_row(adset, col_widths, fill=fill, row_h=row_height, font_size=body_font_size)
            if adset.get('id') == 'unattributed':
                self.set_font('Helvetica', '', max(6, int(body_font_size - 1)))
                for term in adset.get('terms', []):
                    self.draw_row(term, col_widths, fill=fill, indent=True, row_h=row_height, font_size=max(6, body_font_size - 1))
                self.set_font('Helvetica', 'B', int(body_font_size))
            fill = not fill

        self.set_font('Helvetica', 'B', int(body_font_size + 1))
        grand_totals_row = {
            "name": "GRAND TOTAL",
            "spend": grand_totals["spend"],
            "totalOrders": grand_totals["totalOrders"],
            "deliveredOrders": grand_totals["deliveredOrders"],
            "rtoOrders": grand_totals["rtoOrders"],
            "cancelledOrders": grand_totals["cancelledOrders"],
            "inTransitOrders": grand_totals["inTransitOrders"],
            "processingOrders": grand_totals["processingOrders"],
            "deliveredRevenue": grand_totals["deliveredRevenue"]
        }
        self.draw_row(grand_totals_row, col_widths, fill=True, is_total=True, row_h=row_height, font_size=body_font_size + 1)

        try:
            self._draw_signature_block()
        except Exception:
            pass

    def _draw_signature_block(self):
        candidate_paths = [
            'app/static/assets/signature.png',
            'app/static/assets/image.png',
            'image.png'
        ]
        sig_path = None
        for p in candidate_paths:
            if os.path.exists(p):
                sig_path = p
                break

        if not sig_path:
            return

        img_w = 36
        spacing = 2
        bottom_margin = self.b_margin + 6
        approx_img_h = img_w * 0.35
        text_h = 6
        total_block_h = text_h + spacing + approx_img_h
        x_img = self.w - self.r_margin - img_w
        y_top = self.h - bottom_margin - total_block_h

        try:
            self.set_xy(x_img, y_top)
            try:
                self.set_font('Helvetica', 'BI', 9)
            except Exception:
                self.set_font('Helvetica', 'B', 9)
            self.set_text_color(34, 44, 67)
            self.cell(img_w, text_h, 'Created By', 0, 1, 'C')
            img_y = y_top + text_h + spacing
            self.image(sig_path, x=x_img, y=img_y, w=img_w)
            self.set_text_color(0, 0, 0)
        except Exception:
            pass

    def draw_row(self, data, widths, fill, row_h=10, font_size=8, is_total=False, indent=False):
        total_orders = data.get('totalOrders', 0)
        spend = data.get('spend', 0) or 0
        delivered_revenue = data.get('deliveredRevenue', 0) or 0

        delivered = data.get('deliveredOrders', 0) or 0
        rto = data.get('rtoOrders', 0) or 0
        cancelled = data.get('cancelledOrders', 0) or 0
        denom = delivered + rto + cancelled
        rto_rate = ((rto + cancelled) / denom) if denom > 0 else 0

        cpo = (spend / total_orders) if total_orders > 0 else 0
        roas = (delivered_revenue / spend) if spend > 0 else 0

        self.set_fill_color(243, 244, 246)
        if is_total:
            self.set_fill_color(220, 220, 220)

        name = sanitize_string(data.get('name', 'N/A'))
        if is_total:
            name = "GRAND TOTAL"
        if indent:
            name = f"    - {name}"

        font_style = 'B' if (not indent and not is_total) else ('B' if is_total else '')
        try:
            self.set_font('Helvetica', font_style, int(font_size))
        except Exception:
            self.set_font('Helvetica', font_style, 8)

        self.cell(widths[0], row_h, name, 1, 0, 'L' if indent or not is_total else 'C', fill=fill)
        self.cell(widths[1], row_h, f"{spend:,.0f}", 1, 0, 'R', fill=fill)
        self.cell(widths[2], row_h, f"{delivered_revenue:,.0f}", 1, 0, 'R', fill=fill)
        self.cell(widths[3], row_h, str(total_orders), 1, 0, 'C', fill=fill)
        self.cell(widths[4], row_h, str(int(data.get('deliveredOrders', 0))), 1, 0, 'C', fill=fill)
        self.cell(widths[5], row_h, str(int(data.get('rtoOrders', 0))), 1, 0, 'C', fill=fill)
        self.cell(widths[6], row_h, str(int(data.get('cancelledOrders', 0))), 1, 0, 'C', fill=fill)
        self.cell(widths[7], row_h, str(int(data.get('inTransitOrders', 0))), 1, 0, 'C', fill=fill)
        self.cell(widths[8], row_h, str(int(data.get('processingOrders', 0))), 1, 0, 'C', fill=fill)
        self.cell(widths[9], row_h, f"{rto_rate:.1%}", 1, 0, 'C', fill=fill)
        self.cell(widths[10], row_h, f"{cpo:,.0f}", 1, 0, 'R', fill=fill)

        if not is_total:
            if roas >= 2.0:
                self.set_text_color(0, 128, 0)
            elif roas < 1.0:
                self.set_text_color(255, 0, 0)

        self.cell(widths[11], row_h, f"{roas:.2f}x", 1, 1, 'C', fill=fill)
        self.set_text_color(0, 0, 0)

def sanitize_string(text):
    return str(text).encode('latin-1', 'replace').decode('latin-1')

@pdf_bp.route('/download-dashboard-pdf', methods=['POST'])
@token_required
def download_dashboard_pdf():
    since = request.args.get('since')
    until = request.args.get('until')
    adset_data = request.get_json()

    if not adset_data:
        return "No data provided", 400

    try:
        pdf = PDF()
        pdf.add_page()
        pdf.create_summary(adset_data, since, until)
        pdf.create_table(adset_data)

        pdf_output = pdf.output(dest='S')
        if isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output

        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.seek(0)

        return Response(
            pdf_buffer.getvalue(),
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment;filename=adset_report_{since}_to_{until}.pdf'}
        )
    except Exception:
        print(f"--- [CRITICAL PDF ERROR] ---")
        traceback.print_exc()
        return "An error occurred during PDF generation.", 500