from datacite import DataCiteRESTClient
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django import forms
from django.forms import formset_factory
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.contrib.sites.shortcuts import get_current_site
from django.db import transaction

from .datacite_form import DataCiteForm, CreatorForm, TitleForm, SubjectForm, ContributorForm, DescriptionForm, \
    RightsForm, AlternateIdentifierForm, RelatedIdentifierForm, FundingReferenceForm
from .models import (
    DataCite, Curtain, DataFilterList, ExtraProperties, UserAPIKey, UserPublicKey,
    SocialPlatform, KinaseLibraryModel, CurtainAccessToken, DataAESEncryptionFactors,
    DataHash, LastAccess, Announcement, PermanentLinkRequest, CurtainCollection
)
from django.conf import settings


class ExtraPropertiesInline(admin.StackedInline):
    model = ExtraProperties
    can_delete = False
    verbose_name_plural = 'Extra Properties'
    fk_name = 'user'
    fields = ('curtain_link_limits', 'curtain_link_limit_exceed', 'curtain_post', 'social_platform', 'default_public_key')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj:
            formset.form.base_fields['default_public_key'].queryset = UserPublicKey.objects.filter(user=obj)
        else:
            if 'default_public_key' in formset.form.base_fields:
                formset.form.base_fields['default_public_key'].queryset = UserPublicKey.objects.none()
        return formset


class UserAPIKeyInline(admin.TabularInline):
    model = UserAPIKey
    extra = 0
    readonly_fields = ('created', 'prefix')
    fields = ('name', 'prefix', 'can_read', 'can_create', 'can_update', 'can_delete', 'revoked')


class UserPublicKeyInline(admin.TabularInline):
    model = UserPublicKey
    extra = 0
    readonly_fields = ('created', 'public_key_display')
    fields = ('created', 'public_key_display')

    def public_key_display(self, obj):
        if obj.pk and obj.public_key:
            return format_html('<code style="font-size: 10px;">{}</code>', obj.public_key[:100].hex() + '...' if len(obj.public_key) > 100 else obj.public_key.hex())
        return '-'
    public_key_display.short_description = 'Public Key (hex)'


class CustomUserAdmin(BaseUserAdmin):
    inlines = (ExtraPropertiesInline, UserAPIKeyInline, UserPublicKeyInline)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 'curtain_count')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')

    def curtain_count(self, obj):
        return obj.curtain.count()
    curtain_count.short_description = 'Curtains'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('curtain')


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


admin.site.site_header = 'CurtainBE Administration'
admin.site.site_title = 'CurtainBE Admin'
admin.site.index_title = 'Welcome to CurtainBE Administration'


class ExpiredStatusFilter(admin.SimpleListFilter):
    """
    Custom filter for curtain expiry status
    """
    title = 'expiry status'
    parameter_name = 'expiry_status'

    def lookups(self, request, model_admin):
        return (
            ('permanent', 'Permanent'),
            ('active', 'Active (Not Expired)'),
            ('expired', 'Expired'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'permanent':
            return queryset.filter(permanent=True)
        elif self.value() == 'active':
            active_ids = [c.id for c in queryset.filter(permanent=False) if not c.is_expired]
            return queryset.filter(id__in=active_ids)
        elif self.value() == 'expired':
            expired_ids = [c.id for c in queryset.filter(permanent=False) if c.is_expired]
            return queryset.filter(id__in=expired_ids)
        return queryset


class DataAESEncryptionFactorsInline(admin.TabularInline):
    model = DataAESEncryptionFactors
    extra = 0
    readonly_fields = ('created', 'encrypted_with')
    fields = ('created', 'encrypted_decryption_key', 'encrypted_iv', 'encrypted_with')


class DataHashInline(admin.TabularInline):
    model = DataHash
    extra = 0
    readonly_fields = ('created',)
    fields = ('created', 'hash')


class CurtainAccessTokenInline(admin.TabularInline):
    model = CurtainAccessToken
    extra = 0
    readonly_fields = ('created', 'token')
    fields = ('created', 'token')


class LastAccessInline(admin.TabularInline):
    model = LastAccess
    extra = 0
    readonly_fields = ('last_access',)
    fields = ('last_access',)
    max_num = 1


@admin.register(Curtain)
class CurtainAdmin(admin.ModelAdmin):
    list_display = ('link_id_short', 'curtain_type', 'created', 'last_access_display', 'owner_list', 'enable', 'permanent', 'expired_status', 'encrypted')
    list_filter = ('curtain_type', 'enable', 'permanent', 'encrypted', ExpiredStatusFilter, 'created', 'updated')
    search_fields = ('link_id', 'description', 'owners__username')
    readonly_fields = ('created', 'updated', 'link_id', 'expired_status', 'last_access_display')
    filter_horizontal = ('owners',)
    date_hierarchy = 'created'
    list_per_page = 20

    fieldsets = (
        ('Basic Information', {
            'fields': ('link_id', 'curtain_type', 'description')
        }),
        ('File & Ownership', {
            'fields': ('file', 'owners')
        }),
        ('Settings', {
            'fields': ('enable', 'permanent', 'encrypted', 'expiry_duration', 'expired_status')
        }),
        ('Timestamps', {
            'fields': ('created', 'updated', 'last_access_display'),
            'classes': ('collapse',)
        }),
    )

    inlines = [LastAccessInline, CurtainAccessTokenInline, DataAESEncryptionFactorsInline, DataHashInline]

    def link_id_short(self, obj):
        return str(obj.link_id)[:8] + '...'
    link_id_short.short_description = 'Link ID'

    def owner_list(self, obj):
        owners = obj.owners.all()
        if owners:
            return ', '.join([owner.username for owner in owners[:3]])
        return 'None'
    owner_list.short_description = 'Owners'

    def last_access_display(self, obj):
        last_access_record = obj.last_access.order_by('-last_access').first()
        if last_access_record:
            return last_access_record.last_access.strftime('%Y-%m-%d %H:%M:%S')
        return 'Never'
    last_access_display.short_description = 'Last Access'

    def expired_status(self, obj):
        if obj.permanent:
            return format_html('<span style="color: green;">Permanent</span>')
        elif obj.is_expired:
            return format_html('<span style="color: red;">Expired</span>')
        else:
            return format_html('<span style="color: orange;">Active</span>')
    expired_status.short_description = 'Status'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('owners', 'last_access')


@admin.register(ExtraProperties)
class ExtraPropertiesAdmin(admin.ModelAdmin):
    list_display = ('user', 'curtain_link_limits', 'social_platform', 'curtain_link_limit_exceed', 'curtain_post')
    list_filter = ('curtain_link_limit_exceed', 'curtain_post', 'social_platform')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user',)

    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Curtain Settings', {
            'fields': ('curtain_link_limits', 'curtain_link_limit_exceed', 'curtain_post')
        }),
        ('Social & Encryption', {
            'fields': ('social_platform', 'default_public_key')
        }),
    )


@admin.register(UserAPIKey)
class UserAPIKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'prefix', 'created', 'can_read', 'can_create', 'can_update', 'can_delete', 'revoked')
    list_filter = ('can_read', 'can_create', 'can_update', 'can_delete', 'revoked', 'created')
    search_fields = ('name', 'user__username', 'prefix')
    readonly_fields = ('created', 'prefix')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'user', 'prefix', 'created')
        }),
        ('Permissions', {
            'fields': ('can_read', 'can_create', 'can_update', 'can_delete')
        }),
        ('Status', {
            'fields': ('revoked',)
        }),
    )


@admin.register(UserPublicKey)
class UserPublicKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'created', 'public_key_preview')
    list_filter = ('created',)
    search_fields = ('user__username',)
    readonly_fields = ('created',)
    date_hierarchy = 'created'

    def public_key_preview(self, obj):
        return str(obj.public_key)[:50] + '...' if obj.public_key else 'N/A'
    public_key_preview.short_description = 'Public Key'


@admin.register(SocialPlatform)
class SocialPlatformAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(DataFilterList)
class DataFilterListAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'user', 'default')
    list_filter = ('category', 'default')
    search_fields = ('name', 'category', 'user__username')

    fieldsets = (
        ('Filter Information', {
            'fields': ('name', 'category', 'data')
        }),
        ('Settings', {
            'fields': ('default', 'user')
        }),
    )


@admin.register(KinaseLibraryModel)
class KinaseLibraryModelAdmin(admin.ModelAdmin):
    list_display = ('entry', 'position', 'residue', 'data_preview')
    list_filter = ('residue',)
    search_fields = ('entry', 'data')

    def data_preview(self, obj):
        return str(obj.data)[:50] + '...' if len(str(obj.data)) > 50 else str(obj.data)
    data_preview.short_description = 'Data'


@admin.register(CurtainAccessToken)
class CurtainAccessTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'curtain_link', 'created', 'token_preview')
    list_filter = ('created',)
    search_fields = ('curtain__link_id', 'token')
    readonly_fields = ('created',)
    date_hierarchy = 'created'

    def curtain_link(self, obj):
        if obj.curtain:
            return str(obj.curtain.link_id)[:8] + '...'
        return 'N/A'
    curtain_link.short_description = 'Curtain'

    def token_preview(self, obj):
        return str(obj.token)[:30] + '...' if len(str(obj.token)) > 30 else str(obj.token)
    token_preview.short_description = 'Token'


@admin.register(DataAESEncryptionFactors)
class DataAESEncryptionFactorsAdmin(admin.ModelAdmin):
    list_display = ('id', 'curtain_link', 'created', 'encrypted_with')
    list_filter = ('created',)
    search_fields = ('curtain__link_id',)
    readonly_fields = ('created',)
    date_hierarchy = 'created'

    def curtain_link(self, obj):
        if obj.curtain:
            return str(obj.curtain.link_id)[:8] + '...'
        return 'N/A'
    curtain_link.short_description = 'Curtain'


@admin.register(DataHash)
class DataHashAdmin(admin.ModelAdmin):
    list_display = ('id', 'curtain_link', 'created', 'hash_preview')
    list_filter = ('created',)
    search_fields = ('curtain__link_id', 'hash')
    readonly_fields = ('created',)
    date_hierarchy = 'created'

    def curtain_link(self, obj):
        if obj.curtain:
            return str(obj.curtain.link_id)[:8] + '...'
        return 'N/A'
    curtain_link.short_description = 'Curtain'

    def hash_preview(self, obj):
        return str(obj.hash)[:20] + '...' if len(str(obj.hash)) > 20 else str(obj.hash)
    hash_preview.short_description = 'Hash'


@admin.register(LastAccess)
class LastAccessAdmin(admin.ModelAdmin):
    list_display = ('id', 'curtain_link', 'last_access')
    list_filter = ('last_access',)
    search_fields = ('curtain__link_id',)
    readonly_fields = ('last_access',)
    date_hierarchy = 'last_access'

    def curtain_link(self, obj):
        if obj.curtain:
            return str(obj.curtain.link_id)[:8] + '...'
        return 'N/A'
    curtain_link.short_description = 'Curtain'

class DataCiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'title_preview', 'user', 'status_badge', 'doi_link', 'curtain_link', 'has_local_file', 'lock', 'created', 'updated')
    list_filter = ('status', 'lock', 'created', 'updated')
    search_fields = ('title', 'doi', 'user__username', 'contact_email', 'curtain__link_id')
    readonly_fields = ('created', 'updated', 'doi', 'local_file', 'local_file_link')
    date_hierarchy = 'updated'
    list_per_page = 20
    actions = ['approve_datacite', 'reject_datacite', 'unlock_datacite']

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'doi', 'status', 'lock')
        }),
        ('User Information', {
            'fields': ('user', 'contact_email')
        }),
        ('Data', {
            'fields': ('curtain', 'collection', 'local_file', 'local_file_link', 'form_data', 'pii_statement'),
            'description': 'Select either a single curtain or a collection. If collection is selected, all enabled curtains in the collection will be included as relatedIdentifiers in DataCite metadata.'
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',)
        }),
    )

    def title_preview(self, obj):
        if obj.title:
            return str(obj.title)[:50] + '...' if len(str(obj.title)) > 50 else str(obj.title)
        return 'N/A'
    title_preview.short_description = 'Title'

    def status_badge(self, obj):
        colors = {
            'pending': '#FFA500',
            'published': '#28a745',
            'draft': '#6c757d',
            'rejected': '#dc3545'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def doi_link(self, obj):
        if obj.doi:
            return format_html('<a href="https://doi.org/{}" target="_blank">{}</a>', obj.doi, obj.doi)
        return 'N/A'
    doi_link.short_description = 'DOI'

    def curtain_link(self, obj):
        if obj.curtain:
            return str(obj.curtain.link_id)[:8] + '...'
        return 'N/A'
    curtain_link.short_description = 'Curtain'

    def has_local_file(self, obj):
        if obj.local_file:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    has_local_file.short_description = 'Local File'

    def local_file_link(self, obj):
        if obj.local_file:
            file_url = reverse('datacite_file', kwargs={'datacite_id': obj.id})
            return format_html('<a href="{}" target="_blank">{}</a>', file_url, file_url)
        return 'N/A'
    local_file_link.short_description = 'Public File URL'

    def reject_datacite(self, request, queryset):
        count = queryset.update(status='rejected')
        for datacite in queryset:
            datacite.send_notification()
        self.message_user(request, f"{count} DataCite(s) rejected successfully.")
    reject_datacite.short_description = "Reject selected DataCite(s)"

    def unlock_datacite(self, request, queryset):
        count = queryset.update(lock=False)
        self.message_user(request, f"{count} DataCite(s) unlocked successfully.")
    unlock_datacite.short_description = "Unlock selected DataCite(s)"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user', 'curtain')

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
        context['relatedIdentifiers_formset'] = related_identifiers_formset
        context['fundingReferences_formset'] = fundingReferences_formset
        context['datacite'] = datacite


        return render(request, 'admin/review_datacite.html', context)

    def approve_datacite(self, request, queryset):
        for datacite in queryset:
            client = DataCiteRESTClient(
                username=settings.DATACITE_USERNAME,
                password=settings.DATACITE_PASSWORD,
                prefix=settings.DATACITE_PREFIX,
                test_mode=settings.DATACITE_TEST_MODE
            )
            client.show_doi(datacite.doi)
            datacite.status = 'published'
            datacite.save()

            datacite.send_notification()
        self.message_user(request, "Selected DataCite(s) approved successfully.")


    approve_datacite.short_description = "Approve selected DataCite(s)"

admin.site.register(DataCite, DataCiteAdmin)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'announcement_type_badge', 'priority_badge', 'is_active', 'is_visible_status', 'starts_at', 'expires_at', 'show_on_login', 'created')
    list_filter = ('announcement_type', 'priority', 'is_active', 'show_on_login', 'dismissible')
    search_fields = ('title', 'content')
    readonly_fields = ('created', 'updated', 'created_by', 'is_visible_status')
    ordering = ('-priority', '-created')

    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'content', 'announcement_type', 'priority')
        }),
        ('Visibility Settings', {
            'fields': ('is_active', 'show_on_login', 'dismissible', 'starts_at', 'expires_at')
        }),
        ('Metadata', {
            'fields': ('created', 'updated', 'created_by'),
            'classes': ('collapse',)
        }),
    )

    def announcement_type_badge(self, obj):
        colors = {
            'info': '#3498db',
            'warning': '#f39c12',
            'success': '#2ecc71',
            'error': '#e74c3c',
            'maintenance': '#9b59b6'
        }
        color = colors.get(obj.announcement_type, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_announcement_type_display()
        )
    announcement_type_badge.short_description = 'Type'

    def priority_badge(self, obj):
        colors = {
            'low': '#95a5a6',
            'medium': '#3498db',
            'high': '#f39c12',
            'critical': '#e74c3c'
        }
        color = colors.get(obj.priority, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_priority_display()
        )
    priority_badge.short_description = 'Priority'

    def is_visible_status(self, obj):
        if obj.is_visible:
            return format_html('<span style="color: green; font-weight: bold;">✓ Visible</span>')
        return format_html('<span style="color: red; font-weight: bold;">✗ Not Visible</span>')
    is_visible_status.short_description = 'Visibility'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PermanentLinkRequest)
class PermanentLinkRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'curtain_link', 'requested_by', 'request_type_badge', 'requested_expiry_months', 'status_badge', 'requested_at', 'reviewed_at', 'reviewed_by')
    list_filter = ('status', 'request_type', 'requested_at', 'reviewed_at')
    search_fields = ('curtain__link_id', 'requested_by__username', 'reviewed_by__username', 'reason', 'admin_notes')
    readonly_fields = ('requested_at', 'reviewed_at', 'curtain_link', 'requested_by_username')
    ordering = ('-requested_at',)
    actions = ['approve_requests', 'reject_requests']

    fieldsets = (
        ('Request Information', {
            'fields': ('curtain', 'curtain_link', 'requested_by', 'requested_by_username', 'request_type', 'requested_expiry_months', 'reason', 'requested_at')
        }),
        ('Review Information', {
            'fields': ('status', 'reviewed_by', 'reviewed_at', 'admin_notes')
        }),
    )

    def curtain_link(self, obj):
        if obj.curtain:
            return format_html(
                '<a href="{}" target="_blank">{}</a>',
                reverse('admin:curtain_curtain_change', args=[obj.curtain.id]),
                obj.curtain.link_id
            )
        return '-'
    curtain_link.short_description = 'Curtain'

    def requested_by_username(self, obj):
        return obj.requested_by.username
    requested_by_username.short_description = 'Requested By'

    def request_type_badge(self, obj):
        colors = {
            'permanent': '#9b59b6',
            'extend': '#3498db'
        }
        color = colors.get(obj.request_type, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_request_type_display()
        )
    request_type_badge.short_description = 'Request Type'

    def status_badge(self, obj):
        colors = {
            'pending': '#f39c12',
            'approved': '#2ecc71',
            'rejected': '#e74c3c'
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def save_model(self, request, obj, form, change):
        """
        Handle status changes when editing individual requests.
        """
        if change:
            old_obj = PermanentLinkRequest.objects.get(pk=obj.pk)
            old_status = old_obj.status
            new_status = obj.status

            if old_status == 'pending' and new_status == 'approved':
                with transaction.atomic():
                    obj.approve(request.user)
                if obj.request_type == 'permanent':
                    self.message_user(request, f'Request approved and curtain made permanent successfully.', level='success')
                else:
                    self.message_user(request, f'Request approved and expiry duration extended to {obj.requested_expiry_months} months.', level='success')
                return
            elif old_status == 'pending' and new_status == 'rejected':
                admin_notes = obj.admin_notes
                with transaction.atomic():
                    obj.reject(request.user, admin_notes)
                self.message_user(request, f'Request rejected successfully.', level='success')
                return

        super().save_model(request, obj, form, change)

    def approve_requests(self, request, queryset):
        """
        Admin action to approve selected permanent link requests.
        """
        pending_requests = queryset.filter(status='pending')
        count = 0
        for req in pending_requests:
            with transaction.atomic():
                req.approve(request.user)
            count += 1
        self.message_user(request, f'{count} request(s) approved and curtain(s) updated.')
    approve_requests.short_description = 'Approve selected requests'

    def reject_requests(self, request, queryset):
        """
        Admin action to reject selected permanent link requests.
        """
        pending_requests = queryset.filter(status='pending')
        count = 0
        for req in pending_requests:
            with transaction.atomic():
                req.reject(request.user)
            count += 1
        self.message_user(request, f'{count} request(s) rejected.')
    reject_requests.short_description = 'Reject selected requests'


@admin.register(CurtainCollection)
class CurtainCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'curtain_count', 'created', 'updated')
    list_filter = ('created', 'updated')
    search_fields = ('name', 'description', 'owner__username')
    readonly_fields = ('created', 'updated')
    filter_horizontal = ('curtains',)
    ordering = ('-updated',)

    fieldsets = (
        ('Collection Information', {
            'fields': ('name', 'description', 'owner')
        }),
        ('Curtain Sessions', {
            'fields': ('curtains',)
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',)
        }),
    )

    def curtain_count(self, obj):
        return obj.curtains.count()
    curtain_count.short_description = 'Curtains'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('owner').prefetch_related('curtains')

