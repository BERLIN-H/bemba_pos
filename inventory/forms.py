from django import forms

from inventory.models import PurchaseOrder, Supplier
from restaurant.models import Branch
from restaurant.tenancy import scoped_queryset


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_name', 'email', 'phone', 'address', 'is_active']


class PurchaseOrderForm(forms.ModelForm):
    class Meta:
        model = PurchaseOrder
        fields = ['supplier', 'branch', 'notes']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['supplier'].queryset = scoped_queryset(Supplier.objects.all(), user)
            self.fields['branch'].queryset = scoped_queryset(Branch.objects.all(), user)
