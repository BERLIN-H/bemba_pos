import json
import re

from django import forms
from restaurant.models import (BranchSettings, RestaurantAccount, RestaurantModules, RestaurantNotificationSettings, RestaurantPreferences,
                               RestaurantReceiptSettings, RestaurantSettings)


class CleanFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class BrandingForm(CleanFormMixin, forms.ModelForm):
    class Meta:
        model = RestaurantSettings
        exclude = ('restaurant', 'trade_name', 'logo_url', 'sidebar_logo_url', 'favicon_url', 'cover_image_url', 'login_background_url', 'created_at', 'updated_at')
        labels = {'trade_name': 'Nombre comercial', 'short_name': 'Nombre corto', 'slogan': 'Eslogan', 'logo_file': 'Logotipo principal', 'sidebar_logo_file': 'Logotipo de barra lateral', 'favicon_file': 'Icono del navegador', 'cover_image_file': 'Imagen de portada', 'login_background_file': 'Fondo de inicio de sesión', 'theme': 'Tema', 'primary_color': 'Color principal', 'secondary_color': 'Color secundario', 'button_color': 'Color de botones', 'accent_color': 'Color de acento', 'background_color': 'Color de fondo', 'sidebar_color': 'Color de barra lateral', 'text_color': 'Color del texto', 'selected_color': 'Color de elementos seleccionados', 'font_family': 'Fuente', 'font_size': 'Tamaño de letra', 'title_weight': 'Grosor de títulos', 'square_corners': 'Usar bordes cuadrados', 'compact_tables': 'Tablas compactas', 'dark_mode': 'Modo oscuro'}
        widgets = {'slogan': forms.TextInput(attrs={'placeholder': 'Una frase para tu restaurante'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('primary_color', 'secondary_color', 'button_color', 'accent_color', 'background_color', 'sidebar_color', 'text_color', 'selected_color'):
            self.fields[name].widget = forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color'})
        for name in ('logo_file', 'sidebar_logo_file', 'cover_image_file', 'login_background_file'):
            self.fields[name].widget.attrs['accept'] = 'image/png,image/jpeg,image/webp'
        self.fields['favicon_file'].widget.attrs['accept'] = 'image/png,image/x-icon'
        self.fields['title_weight'].widget.attrs.update({'min': '500', 'max': '900', 'step': '100'})

    def clean(self):
        cleaned = super().clean()
        for name in ('primary_color', 'secondary_color', 'button_color', 'accent_color', 'background_color', 'sidebar_color', 'text_color', 'selected_color'):
            value = cleaned.get(name, '')
            if value and not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                self.add_error(name, 'Usa un color hexadecimal válido, por ejemplo #17324D.')
        return cleaned


class RestaurantInfoForm(CleanFormMixin, forms.ModelForm):
    class Meta:
        model = RestaurantAccount
        fields = ('business_name', 'legal_name', 'tax_id', 'email', 'phone')
        labels = {'business_name': 'Nombre comercial', 'legal_name': 'Razón social', 'tax_id': 'NIT', 'email': 'Correo electrónico', 'phone': 'Teléfono'}


class PreferencesForm(CleanFormMixin, forms.ModelForm):
    social_links_text = forms.CharField(label='Redes sociales (JSON)', required=False, widget=forms.Textarea(attrs={'rows': 3, 'placeholder': '{"instagram":"https://..."}'}))
    business_hours_text = forms.CharField(label='Horarios (JSON)', required=False, widget=forms.Textarea(attrs={'rows': 3, 'placeholder': '{"lunes":"09:00-18:00"}'}))

    class Meta:
        model = RestaurantPreferences
        exclude = ('restaurant', 'social_links', 'business_hours', 'updated_at')
        labels = {'address': 'Dirección', 'city': 'Ciudad', 'business_type': 'Tipo de establecimiento', 'timezone': 'Zona horaria', 'currency': 'Moneda', 'table_service': 'Trabaja con mesas', 'takeaway': 'Pedidos para llevar', 'delivery': 'Domicilios', 'whatsapp_orders': 'Pedidos por WhatsApp', 'cancellation_approval': 'Exigir autorización para cancelar', 'manual_discounts': 'Permitir descuentos manuales', 'tips': 'Manejar propinas', 'split_bills': 'Permitir dividir cuentas', 'open_accounts': 'Permitir cuentas abiertas', 'require_customer': 'Exigir identificar al cliente', 'inventory_enabled': 'Control de inventario', 'cash_open_required': 'Exigir apertura de caja', 'cash_withdrawals': 'Permitir retiros de caja', 'cash_deposits': 'Permitir entradas de dinero', 'refunds_allowed': 'Permitir devoluciones'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['social_links_text'].initial = json.dumps(self.instance.social_links, ensure_ascii=False, indent=2)
            self.fields['business_hours_text'].initial = json.dumps(self.instance.business_hours, ensure_ascii=False, indent=2)

    def clean_social_links_text(self):
        return self._clean_json(self.cleaned_data.get('social_links_text', ''), 'Redes sociales')

    def clean_business_hours_text(self):
        return self._clean_json(self.cleaned_data.get('business_hours_text', ''), 'Horarios')

    @staticmethod
    def _clean_json(value, label):
        if not value.strip():
            return {}
        try:
            result = json.loads(value)
        except json.JSONDecodeError:
            raise forms.ValidationError(f'{label} debe ser JSON válido.')
        if not isinstance(result, dict):
            raise forms.ValidationError(f'{label} debe ser un objeto JSON.')
        return result

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.social_links = self.cleaned_data['social_links_text']
        instance.business_hours = self.cleaned_data['business_hours_text']
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ModulesForm(CleanFormMixin, forms.ModelForm):
    class Meta:
        model = RestaurantModules
        exclude = ('restaurant', 'updated_at')
        labels = {'tables': 'Mesas', 'delivery': 'Domicilios', 'takeaway': 'Para llevar', 'kitchen_kds': 'Cocina KDS', 'inventory': 'Inventario', 'recipes': 'Recetas', 'customers': 'Clientes', 'suppliers': 'Proveedores', 'reservations': 'Reservaciones', 'reports': 'Reportes'}


class ReceiptForm(CleanFormMixin, forms.ModelForm):
    class Meta:
        model = RestaurantReceiptSettings
        exclude = ('restaurant', 'logo_url', 'updated_at')
        labels = {'header': 'Encabezado', 'logo_file': 'Logotipo impreso', 'address': 'Dirección impresa', 'phone': 'Teléfono impreso', 'thank_you_message': 'Mensaje de agradecimiento', 'footer': 'Pie de página', 'paper_size': 'Tamaño de papel', 'show_customer': 'Mostrar cliente', 'show_tax': 'Mostrar impuestos', 'show_cashier': 'Mostrar cajero', 'kitchen_ticket_note': 'Nota para comandas de cocina'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['logo_file'].widget.attrs['accept'] = 'image/png,image/jpeg,image/webp'


class NotificationsForm(CleanFormMixin, forms.ModelForm):
    class Meta:
        model = RestaurantNotificationSettings
        exclude = ('restaurant', 'updated_at')
        labels = {'new_orders': 'Nuevos pedidos', 'delayed_orders': 'Pedidos demorados', 'low_stock': 'Bajo inventario', 'cash_close': 'Cierre de caja', 'cancelled_sales': 'Ventas canceladas', 'cash_discrepancies': 'Diferencias de caja', 'new_employees': 'Nuevos empleados', 'daily_reports': 'Reportes diarios', 'sales_summary': 'Resumen de ventas', 'in_app': 'Dentro del POS', 'email': 'Correo electrónico', 'whatsapp': 'WhatsApp'}


class BranchSettingsForm(CleanFormMixin, forms.ModelForm):
    class Meta:
        model = BranchSettings
        exclude = ('branch', 'logo_url', 'updated_at')
        labels = {'inherit_restaurant': 'Heredar la configuración del restaurante', 'timezone': 'Zona horaria', 'currency': 'Moneda', 'primary_color': 'Color principal', 'logo_file': 'Logotipo de sede'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['logo_file'].widget.attrs['accept'] = 'image/png,image/jpeg,image/webp'
