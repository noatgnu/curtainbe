from datacite import DataCiteRESTClient
from django.contrib import admin
from django import forms
from django.forms import formset_factory
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse

from .datacite_form import DataCiteForm, CreatorForm, TitleForm, SubjectForm, ContributorForm, DescriptionForm, \
    RightsForm, AlternateIdentifierForm, RelatedIdentifierForm, FundingReferenceForm
from .models import DataCite
from django.conf import settings
from curtain.models import Curtain, DataFilterList, DataCite


@admin.register(Curtain)
class CurtainAdmin(admin.ModelAdmin):
    pass


@admin.register(DataFilterList)
class DataFilterListAdmin(admin.ModelAdmin):
    pass

class DataCiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'status', 'created')
    actions = ['approve_datacite']

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('review/<int:datacite_id>/', self.admin_site.admin_view(self.review_datacite), name='review_datacite'),
        ]
        return custom_urls + urls

    def review_datacite(self, request, datacite_id):
        context = dict(
            self.admin_site.each_context(request),
            title='Review DataCite',
            datacite_id=datacite_id,
        )
        datacite = self.get_object(request, datacite_id)
        form_data = datacite.form_data

        if request.method == 'POST':
            form = DataCiteForm(request.POST, instance=datacite)
            creators_formset = formset_factory(CreatorForm)(request.POST, prefix='creators')
            titles_formset = formset_factory(TitleForm)(request.POST, prefix='titles')
            # Add other formsets similarly
            if form.is_valid() and creators_formset.is_valid() and titles_formset.is_valid():
                datacite = form.save(commit=False)
                if datacite.status == 'published':
                    client = DataCiteRESTClient(
                        username=settings.DATACITE_USERNAME,
                        password=settings.DATACITE_PASSWORD,
                        prefix=settings.DATACITE_PREFIX,
                        test_mode=settings.DATACITE_TEST_MODE
                    )
                    client.show_doi(datacite.doi)
                datacite.save()
                self.message_user(request, "DataCite status updated successfully.")
                return redirect('admin:curtain_datacite_changelist')
        else:
            initial_data = {
                'schemaVersion': form_data.get('schemaVersion', ''),
                'prefix': form_data.get('prefix', ''),
                'suffix': form_data.get('suffix', ''),
                'url': form_data.get('url', ''),
            }
            form = DataCiteForm(instance=datacite, initial=initial_data)
            creators_formset = formset_factory(CreatorForm, extra=0)(initial=form_data.get('creators', []),
                                                                     prefix='creators')
            titles_formset = formset_factory(TitleForm, extra=0)(initial=form_data.get('titles', []), prefix='titles')
            subjects_formset = formset_factory(SubjectForm, extra=0)(initial=form_data.get('subjects', []),
                                                                     prefix='subjects')
            contributors_formset = formset_factory(ContributorForm, extra=0)(initial=form_data.get('contributors', []),
                                                                             prefix='contributors')
            descriptions_formset = formset_factory(DescriptionForm, extra=0)(initial=form_data.get('descriptions', []),
                                                                             prefix='descriptions')
            rightsList_formset = formset_factory(RightsForm, extra=0)(initial=form_data.get('rightsList', []),
                                                                        prefix='rightsList')
            alternateIdentifiers_formset = formset_factory(AlternateIdentifierForm, extra=0)(initial_data.get('alternateIdentifiers', []),
                                                                        prefix='alternateIdentifiers')
            related_identifiers_formset = formset_factory(RelatedIdentifierForm, extra=0)(initial_data.get('relatedIdentifiers', []),
                                                                        prefix='relatedIdentifiers')
            fundingReferences_formset = formset_factory(FundingReferenceForm, extra=0)(initial_data.get('fundingReferences', []),
                                                                        prefix='fundingReferences')

        context['form'] = form
        context['creators_formset'] = creators_formset
        context['titles_formset'] = titles_formset
        context['subjects_formset'] = subjects_formset
        context['contributors_formset'] = contributors_formset
        context['descriptions_formset'] = descriptions_formset
        context['rightsList_formset'] = rightsList_formset
        context['alternateIdentifiers_formset'] = alternateIdentifiers_formset
        context['related_identifiers_formset'] = related_identifiers_formset
        context['fundingReferences_formset'] = fundingReferences_formset
        context['datacite'] = datacite


        return render(request, 'admin/review_datacite.html', context)

    def approve_datacite(self, request, queryset):
        for datacite in queryset:
            datacite.status = 'published'
            datacite.save()
        self.message_user(request, "Selected DataCite(s) approved successfully.")
    approve_datacite.short_description = "Approve selected DataCite(s)"

admin.site.register(DataCite, DataCiteAdmin)

