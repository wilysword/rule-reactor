from django import forms

from .models import Occurrence


class BulkResolveForm(forms.Form):
    occurrences = forms.ModelMultipleChoiceField(
        queryset=Occurrence.objects.unresolved(),
        error_messages={'required': 'Must check at least one occurrence to resolve'}
    )
    resolution_message = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        label="Resolution Explanation",
        error_messages={'required': 'Must explain why these occurrences are being resolved.'}
    )
