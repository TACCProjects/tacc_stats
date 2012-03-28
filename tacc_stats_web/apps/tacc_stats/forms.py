from django import forms
from django.forms import ModelForm
from models import Job

CHOICES = (
    ('acct_id', 'ID'),
    ('owner', 'Owner'),
    ('nr_slots', '# of Hosts'),
    ('begin', 'Start Time'),
    ('end', 'End Time'),
    ('mem_MemUsed', 'Memory Used'),
    ('llite_open_work', 'Open Work'),
    ('cpu_irq', 'IRQ'),
    ('timespent', 'Timespent'),
)

class SearchForm(ModelForm):
    sort = forms.ChoiceField(choices=CHOICES)
    begin = forms.DateTimeField()
    end = forms.DateTimeField()

    class Meta:
        model = Job
        fields = ('owner', 'begin', 'end', 'acct_id')
#        widgets = {
#            'begin': forms.DateTimeField(),
#        }

    def __init__(self, *args, **kwargs):
        super(SearchForm, self).__init__(*args, **kwargs)

        for key in self.fields:
            self.fields[key].required = False

