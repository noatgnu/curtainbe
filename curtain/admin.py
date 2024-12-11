from datacite import DataCiteRESTClient
from django.contrib import admin
from django import forms
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponse
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
        datacite = self.get_object(request, datacite_id)
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
            form = DataCiteForm(instance=datacite)
        return render(request, 'admin/review_datacite.html', {'form': form, 'datacite': datacite})

    def approve_datacite(self, request, queryset):
        for datacite in queryset:
            datacite.status = 'published'
            datacite.save()
        self.message_user(request, "Selected DataCite(s) approved successfully.")
    approve_datacite.short_description = "Approve selected DataCite(s)"

admin.site.register(DataCite, DataCiteAdmin)

class DataCiteForm(forms.ModelForm):
    class Meta:
        model = DataCite
        fields = ['form_data', 'status']