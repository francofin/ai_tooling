# stockuploader/forms.py
from __future__ import annotations
from django import forms

MODEL_CHOICES = (
    ("stock", "Stock (symbols)"),
    # add more models here later: ("daily_price", "Daily Prices"), ...
)

class ParquetUploadForm(forms.Form):
    model_key = forms.ChoiceField(choices=MODEL_CHOICES)
    file = forms.FileField(help_text="Upload a .parquet file")

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = (f.name or "").lower()
        if not name.endswith(".parquet"):
            raise forms.ValidationError("Please upload a .parquet file.")
        return f
