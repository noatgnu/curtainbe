from datacite import DataCiteRESTClient
from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse

from .datacite_form import DataCiteForm
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
            if form.is_valid():
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
                'creators': [{'name': creator.get('name', ''), 'nameType': creator.get('nameType', 'Personal')} for
                             creator in form_data.get('creators', [])],
                'titles': [{'title': title.get('title', ''), 'lang': title.get('lang', 'en')} for title in
                           form_data.get('titles', [])],
                'publisher': form_data.get('publisher', {}),
                'publicationYear': form_data.get('publicationYear', ''),
                'types': form_data.get('types', {}),
                'subjects': [{'subject': subject.get('subject', ''), 'subjectScheme': subject.get('subjectScheme', ''),
                              'valueUri': subject.get('valueUri', '')} for subject in form_data.get('subjects', [])],
                'contributors': [
                    {'name': contributor.get('name', ''), 'nameType': contributor.get('nameType', 'Personal')} for
                    contributor in form_data.get('contributors', [])],
                'descriptions': [{'description': description.get('description', ''),
                                  'descriptionType': description.get('descriptionType', 'Abstract')} for description in
                                 form_data.get('descriptions', [])],
                'rightsList': [{'rights': rights.get('rights', ''), 'rightsUri': rights.get('rightsUri', '')} for rights
                               in form_data.get('rightsList', [])],
                'alternateIdentifiers': [{'alternateIdentifier': alt_id.get('alternateIdentifier', ''),
                                          'alternateIdentifierType': alt_id.get('alternateIdentifierType', '')} for
                                         alt_id in form_data.get('alternateIdentifiers', [])],
                'relatedIdentifiers': [{'relatedIdentifier': rel_id.get('relatedIdentifier', ''),
                                        'relatedIdentifierType': rel_id.get('relatedIdentifierType', ''),
                                        'relationType': rel_id.get('relationType', '')} for rel_id in
                                       form_data.get('relatedIdentifiers', [])],
                'fundingReferences': [
                    {'funderName': fund.get('funderName', ''), 'funderIdentifier': fund.get('funderIdentifier', ''),
                     'funderIdentifierType': fund.get('funderIdentifierType', ''),
                     'awardNumber': fund.get('awardNumber', ''), 'awardUri': fund.get('awardUri', ''),
                     'awardTitle': fund.get('awardTitle', '')} for fund in form_data.get('fundingReferences', [])],
            }
            form = DataCiteForm(instance=datacite, initial=initial_data)

        context['form'] = form
        context['datacite'] = datacite
        context['form_data'] = form_data
        return render(request, 'admin/review_datacite.html', context)

    def approve_datacite(self, request, queryset):
        for datacite in queryset:
            datacite.status = 'published'
            datacite.save()
        self.message_user(request, "Selected DataCite(s) approved successfully.")
    approve_datacite.short_description = "Approve selected DataCite(s)"

admin.site.register(DataCite, DataCiteAdmin)

