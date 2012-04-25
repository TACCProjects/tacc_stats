from django import forms
from django.forms import ModelForm
from models import Job
from django.core.validators import RegexValidator

CHOICES = (
    ('acct_id', 'ID'),
    ('owner', 'Owner'),
    ('nr_slots', '# of Hosts'),
    ('begin', 'Start Time'),
    ('end', 'End Time'),
    ('mem_MemUsed', 'Memory Used'),
    ('llite_open_work', 'Open Work'),
    ('cpu_irq', 'IRQ'),
   # ('timespent', 'Timespent'),
)

def validate_date(value):
    if 0:
        raise ValidationError('poop')

class CalendarWidget(forms.TextInput):
    class Media:
        css = {
            'all': ('anytime.css')
        }
        js = ('anytime.js', 'jquery.min.js')

class SearchForm(ModelForm):
    begin = forms.DateTimeField(widget=CalendarWidget)
    end = forms.DateTimeField(widget=CalendarWidget)
#    sort = forms.ChoiceField(choices=CHOICES)
    host = forms.CharField(max_length=100)

    class Meta:
        model = Job
        fields = ('owner', 'acct_id')
#        widgets = {
#            'begin': forms.DateTimeField(),
#        }

    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)

        for key in self.fields:
            self.fields[key].required = False
