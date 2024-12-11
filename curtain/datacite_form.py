from datetime import datetime

from django import forms
from django.forms import ModelForm, formset_factory
from .models import DataCite

class NameIdentifierForm(forms.Form):
    schemeUri = forms.URLField(initial="https://orcid.org/")
    nameIdentifier = forms.CharField(required=False)
    nameIdentifierScheme = forms.CharField(initial="ORCID")

class AffiliationForm(forms.Form):
    name = forms.CharField(required=True)
    affiliationIdentifier = forms.CharField(required=False)
    affiliationIdentifierScheme = forms.CharField(required=False)
    schemeUri = forms.URLField(required=False)

class CreatorForm(forms.Form):
    givenName = forms.CharField(required=False)
    familyName = forms.CharField(required=False)
    name = forms.CharField(required=True)
    nameType = forms.CharField(initial="Personal")
    nameIdentifiers = forms.CharField(widget=forms.HiddenInput(), required=False)
    affiliation = forms.CharField(widget=forms.HiddenInput(), required=False)

class TitleForm(forms.Form):
    title = forms.CharField(required=True)
    lang = forms.CharField(initial="en")

class PublisherForm(forms.Form):
    name = forms.CharField(initial="University of Dundee")
    publisherIdentifier = forms.URLField(initial="https://ror.org/03h2bxq36")
    publisherIdentifierScheme = forms.CharField(initial="ROR")
    schemeUri = forms.URLField(initial="https://ror.org/")

class TypeForm(forms.Form):
    resourceTypeGeneral = forms.CharField(initial="Dataset")
    resourceType = forms.CharField(initial="Interactive visualization of differential analysis datasets")

class SubjectForm(forms.Form):
    subject = forms.CharField(initial="Biological sciences")
    subjectScheme = forms.CharField(initial="OECD REVISED FIELD OF SCIENCE AND TECHNOLOGY (FOS) CLASSIFICATION IN THE FRASCATI MANUAL")
    valueUri = forms.URLField(initial="https://unstats.un.org/wiki/download/attachments/101354089/FOS.pdf?api=v2")

class ContributorForm(forms.Form):
    name = forms.CharField(required=False)
    affiliation = forms.CharField(widget=forms.HiddenInput(), required=False)
    givenName = forms.CharField(required=False)
    familyName = forms.CharField(required=False)
    nameIdentifiers = forms.CharField(widget=forms.HiddenInput(), required=False)
    nameType = forms.CharField(initial="Personal")

class DescriptionForm(forms.Form):
    description = forms.CharField(widget=forms.Textarea, required=True)
    descriptionType = forms.CharField(initial="Abstract")

class RightsForm(forms.Form):
    rights = forms.CharField(initial="Creative Commons Attribution 4.0 International")
    rightsUri = forms.URLField(initial="https://creativecommons.org/licenses/by/4.0/legalcode")

class AlternateIdentifierForm(forms.Form):
    alternateIdentifier = forms.CharField(required=True)
    alternateIdentifierType = forms.CharField(initial="Direct data access URL")

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