from io import BytesIO
import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import FileResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.permissions import role_required
from sales.models import Payment
from restaurant.tenancy import scoped_queryset

logger = logging.getLogger(__name__)


def parse_report_date(value):
    """Parse date from various formats."""
    if not value or not str(value).strip():
        return None
    
    value = str(value).strip()
    
    # Try ISO format (YYYY-MM-DD) from HTML date input
    parsed = parse_date(value)
    if parsed:
        return parsed

    # Fallback for localized date input formats like dd/mm/YYYY
    try:
        from datetime import datetime
        return datetime.strptime(value, '%d/%m/%Y').date()
    except (ValueError, TypeError):
        pass
    
    # Try other common formats
    try:
        from datetime import datetime
        return datetime.strptime(value, '%d-%m-%Y').date()
    except (ValueError, TypeError):
        pass
    
    logger.warning(f'Could not parse date: {value}')
    return None


def get_sales_report_queryset(request):
    payments = scoped_queryset(Payment.objects.select_related('order__table', 'cashier'), request.user).order_by('-created_at')
    
    date_from_input = request.GET.get('date_from', '').strip()
    date_to_input = request.GET.get('date_to', '').strip()
    
    date_from = parse_report_date(date_from_input) if date_from_input else None
    date_to = parse_report_date(date_to_input) if date_to_input else None

    logger.debug(f'Report filter: date_from={date_from}, date_to={date_to}')

    if date_from:
        # Convert date to timezone-aware datetime at start of day
        from datetime import datetime, timedelta
        start_of_day = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
        payments = payments.filter(created_at__gte=start_of_day)
        logger.debug(f'Filtering from: {start_of_day}')
    
    if date_to:
        # Convert date to timezone-aware datetime at start of next day (to include all of date_to)
        from datetime import datetime, timedelta
        end_of_day = timezone.make_aware(datetime.combine(date_to, datetime.min.time())) + timedelta(days=1)
        payments = payments.filter(created_at__lt=end_of_day)
        logger.debug(f'Filtering to: {end_of_day}')

    return payments, date_from, date_to


@login_required
@role_required('admin', 'manager')
def reports_home(request):
    payments, date_from, date_to = get_sales_report_queryset(request)
    totals = payments.aggregate(total=Sum('amount'), transactions=Count('id'))
    method_totals = payments.values('method').annotate(total=Sum('amount'), count=Count('id')).order_by('method')

    return render(request, 'reports/index.html', {
        'payments': payments[:100],
        'total': totals['total'] or 0,
        'transactions': totals['transactions'] or 0,
        'method_totals': method_totals,
        'date_from': date_from,
        'date_to': date_to,
    })


@login_required
@role_required('admin', 'manager')
def sales_pdf(request):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    payments, date_from, date_to = get_sales_report_queryset(request)
    totals = payments.aggregate(total=Sum('amount'), count=Count('id'))
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle('Reporte de ventas Bemba')

    def header():
        pdf.setFont('Helvetica-Bold', 16)
        pdf.drawString(40, 750, 'Bemba POS - Reporte de ventas')
        pdf.setFont('Helvetica', 10)
        pdf.drawString(40, 730, f'Generado: {timezone.localtime().strftime("%Y-%m-%d %H:%M")}')
        if date_from or date_to:
            pdf.drawString(40, 714, f'Periodo: {date_from or "inicio"} a {date_to or "hoy"}')
        pdf.setFont('Helvetica', 10)
        return 696

    y = header()
    for payment in payments.iterator():
        if y < 80:
            pdf.showPage()
            y = header()
        pdf.drawString(40, y, f'Pedido #{payment.order_id} | {payment.get_method_display()} | ${payment.amount} | {timezone.localtime(payment.created_at):%Y-%m-%d %H:%M}')
        y -= 18
    if y < 80:
        pdf.showPage()
        y = header()
    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawString(40, y - 20, f'Transacciones: {totals["count"] or 0}   Total: ${totals["total"] or 0}')
    pdf.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename='bemba-reporte-ventas.pdf')

# Create your views here.
