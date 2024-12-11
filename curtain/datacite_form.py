from datetime import datetime

from django import forms
from django.forms import ModelForm, formset_factory
from .models import DataCite

class CreatorForm(forms.Form):
    givenName = forms.CharField(required=False)
    familyName = forms.CharField(required=False)
    name = forms.CharField(required=False)
    nameType = forms.CharField(initial="Personal", required=False)
    nameIdentifiers = forms.CharField(widget=forms.HiddenInput(), required=False)
    affiliation = forms.CharField(widget=forms.HiddenInput(), required=False)

class TitleForm(forms.Form):
    title = forms.CharField(required=False)
    lang = forms.CharField(initial="en", required=False)

class SubjectForm(forms.Form):
    subject = forms.CharField(initial="Biological sciences", required=False)
    subjectScheme = forms.CharField(initial="OECD REVISED FIELD OF SCIENCE AND TECHNOLOGY (FOS) CLASSIFICATION IN THE FRASCATI MANUAL", required=False)
    valueUri = forms.URLField(initial="https://unstats.un.org/wiki/download/attachments/101354089/FOS.pdf?api=v2", required=False)

class ContributorForm(forms.Form):
    name = forms.CharField(required=False)
    affiliation = forms.CharField(widget=forms.HiddenInput(), required=False)
    givenName = forms.CharField(required=False)
    familyName = forms.CharField(required=False)
    nameIdentifiers = forms.CharField(widget=forms.HiddenInput(), required=False)
    nameType = forms.CharField(initial="Personal", required=False)

class DescriptionForm(forms.Form):
    description = forms.CharField(widget=forms.Textarea, required=False)
    descriptionType = forms.CharField(initial="Abstract", required=False)

class RightsForm(forms.Form):
    rights = forms.CharField(initial="Creative Commons Attribution 4.0 International", required=False)
    rightsUri = forms.URLField(initial="https://creativecommons.org/licenses/by/4.0/legalcode", required=False)

class AlternateIdentifierForm(forms.Form):
    alternateIdentifier = forms.CharField(required=False)
    alternateIdentifierType = forms.CharField(initial="Direct data access URL", required=False)

class RelatedIdentifierForm(forms.Form):
    relatedIdentifier = forms.CharField(required=False)
    relatedIdentifierType = forms.CharField(required=False)
    relationType = forms.CharField(required=False)
    relatedMetadataScheme = forms.CharField(required=False)
    schemeUri = forms.URLField(required=False)
    schemeType = forms.CharField(required=False)
    resourceTypeGeneral = forms.CharField(required=False)

class FundingReferenceForm(forms.Form):
    funderName = forms.CharField(required=False)
    funderIdentifier = forms.CharField(required=False)
    funderIdentifierType = forms.CharField(required=False)
    awardNumber = forms.CharField(required=False)
    awardUri = forms.URLField(required=False)
    awardTitle = forms.CharField(required=False)

class DataCiteForm(ModelForm):
    schemaVersion = forms.URLField(initial="http://datacite.org/schema/kernel-4")
    prefix = forms.CharField(required=True)
    suffix = forms.CharField(required=True)
    url = forms.URLField(required=True)
    creators = formset_factory(CreatorForm, extra=1)
    titles = formset_factory(TitleForm, extra=1)
    publisher = forms.CharField(widget=forms.HiddenInput(), required=False)
    publicationYear = forms.CharField(initial=str(datetime.now().year))
    types = forms.CharField(widget=forms.HiddenInput(), required=False)
    subjects = formset_factory(SubjectForm, extra=1)
    contributors = formset_factory(ContributorForm, extra=1)
    descriptions = formset_factory(DescriptionForm, extra=2)
    rightsList = formset_factory(RightsForm, extra=1)
    alternateIdentifiers = formset_factory(AlternateIdentifierForm, extra=1)
    relatedIdentifiers = formset_factory(RelatedIdentifierForm, extra=1)
    fundingReferences = formset_factory(FundingReferenceForm, extra=1)

    class Meta:
        model = DataCite
        fields = [
            'schemaVersion', 'prefix', 'suffix', 'url', 'publisher',
            'publicationYear', 'types', 'form_data', 'status'
        ]