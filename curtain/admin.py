from datacite import DataCiteRESTClient
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from request.models import Request
from django import forms
from django.forms import formset_factory
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.utils.safestring import mark_safe
from django.contrib.sites.shortcuts import get_current_site
from django.db import models, transaction

from .datacite_form import DataCiteForm, CreatorForm, TitleForm, SubjectForm, ContributorForm, DescriptionForm, \
    RightsForm, AlternateIdentifierForm, RelatedIdentifierForm, FundingReferenceForm
from .models import (
    DataCite, Curtain, DataFilterList, ExtraProperties, UserAPIKey, UserPublicKey,
    SocialPlatform, KinaseLibraryModel, CurtainAccessToken, DataAESEncryptionFactors,
    DataHash, LastAccess, Announcement, PermanentLinkRequest, CurtainCollection
)
from django.conf import settings


class BatchAddOwnerForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Select User",
        help_text="Select a user to add as owner to all selected curtains"
    )


class BatchAddToCollectionForm(forms.Form):
    collection = forms.ModelChoiceField(
        queryset=None,
        label="Select Collection",
        help_text="Select a collection to add the selected curtains to"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import CurtainCollection
        self.fields['collection'].queryset = CurtainCollection.objects.all()


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
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined', 'curtain_count_link', 'collection_count_link')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    def curtain_count_link(self, obj):
        count = obj.curtain.count()
        if count > 0:
            url = reverse('admin:curtain_curtain_changelist') + f'?owners__id__exact={obj.id}'
            return format_html('<a href="{}">{} curtain(s)</a>', url, count)
        return '0'
    curtain_count_link.short_description = 'Curtains'

    def collection_count_link(self, obj):
        count = obj.curtain_collections.count()
        if count > 0:
            url = reverse('admin:curtain_curtaincollection_changelist') + f'?owner__id__exact={obj.id}'
            return format_html('<a href="{}">{} collection(s)</a>', url, count)
        return '0'
    collection_count_link.short_description = 'Collections'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('curtain', 'curtain_collections')


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


admin.site.site_header = 'CurtainBE Administration'
admin.site.site_title = 'CurtainBE Admin'
admin.site.index_title = 'Welcome to CurtainBE Administration'


def admin_dashboard(request):
    from django.utils import timezone
    from datetime import timedelta

    total_curtains = Curtain.objects.count()
    total_users = User.objects.count()
    total_collections = CurtainCollection.objects.count()

    permanent_count = Curtain.objects.filter(permanent=True).count()
    enabled_count = Curtain.objects.filter(enable=True).count()
    expired_count = sum(1 for c in Curtain.objects.filter(permanent=False) if c.is_expired)

    pending_requests = PermanentLinkRequest.objects.filter(status='pending').count()
    pending_datacite = DataCite.objects.filter(status='pending').count()

    week_ago = timezone.now() - timedelta(days=7)
    month_ago = timezone.now() - timedelta(days=30)

    new_curtains_week = Curtain.objects.filter(created__gte=week_ago).count()
    new_curtains_month = Curtain.objects.filter(created__gte=month_ago).count()
    new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
    new_users_month = User.objects.filter(date_joined__gte=month_ago).count()

    recent_curtains = Curtain.objects.order_by('-created')[:10]
    recent_requests = PermanentLinkRequest.objects.filter(status='pending').order_by('-requested_at')[:5]

    context = {
        **admin.site.each_context(request),
        'title': 'Dashboard',
        'total_curtains': total_curtains,
        'total_users': total_users,
        'total_collections': total_collections,
        'permanent_count': permanent_count,
        'enabled_count': enabled_count,
        'expired_count': expired_count,
        'pending_requests': pending_requests,
        'pending_datacite': pending_datacite,
        'new_curtains_week': new_curtains_week,
        'new_curtains_month': new_curtains_month,
        'new_users_week': new_users_week,
        'new_users_month': new_users_month,
        'recent_curtains': recent_curtains,
        'recent_requests': recent_requests,
    }
    return render(request, 'admin/dashboard.html', context)


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


class MultipleIDsFilter(admin.SimpleListFilter):
    """
    Custom filter to search by multiple link_ids (comma, space, or newline separated)
    """
    title = 'multiple link IDs'
    parameter_name = 'link_ids'
    template = 'admin/curtain/multiple_ids_filter.html'

    def lookups(self, request, model_admin):
        return ()

    def queryset(self, request, queryset):
        if self.value():
            import re
            ids = re.split(r'[,\s\n]+', self.value().strip())
            ids = [id.strip() for id in ids if id.strip()]
            if ids:
                return queryset.filter(link_id__in=ids)
        return queryset

    def choices(self, changelist):
        yield {
            'selected': self.value() is None,
            'query_string': changelist.get_query_string(remove=[self.parameter_name]),
            'display': 'All',
            'value': self.value() or '',
        }


class ExpiringSoonFilter(admin.SimpleListFilter):
    """
    Filter for curtains expiring within specified days
    """
    title = 'expiring soon'
    parameter_name = 'expiring_soon'

    def lookups(self, request, model_admin):
        return (
            ('7', 'Within 7 days'),
            ('14', 'Within 14 days'),
            ('30', 'Within 30 days'),
        )

    def queryset(self, request, queryset):
        if self.value():
            from datetime import timedelta
            from django.utils import timezone
            days = int(self.value())
            threshold = timezone.now() + timedelta(days=days)
            expiring_ids = []
            for c in queryset.filter(permanent=False):
                if not c.is_expired:
                    expiry_date = c.created + c.expiry_duration
                    if expiry_date <= threshold:
                        expiring_ids.append(c.id)
            return queryset.filter(id__in=expiring_ids)
        return queryset


class LastAccessFilter(admin.SimpleListFilter):
    """
    Filter for curtains by last access time
    """
    title = 'last access'
    parameter_name = 'last_access_days'

    def lookups(self, request, model_admin):
        return (
            ('never', 'Never accessed'),
            ('7', 'No access in 7 days'),
            ('30', 'No access in 30 days'),
            ('90', 'No access in 90 days'),
        )

    def queryset(self, request, queryset):
        if self.value():
            from datetime import timedelta
            from django.utils import timezone

            if self.value() == 'never':
                curtains_with_access = LastAccess.objects.values_list('curtain_id', flat=True).distinct()
                return queryset.exclude(id__in=curtains_with_access)
            else:
                days = int(self.value())
                threshold = timezone.now() - timedelta(days=days)
                old_access_ids = []
                for c in queryset:
                    last_access = c.last_access.order_by('-last_access').first()
                    if not last_access or last_access.last_access < threshold:
                        old_access_ids.append(c.id)
                return queryset.filter(id__in=old_access_ids)
        return queryset


class OwnerCountFilter(admin.SimpleListFilter):
    """
    Filter by number of owners
    """
    title = 'owner count'
    parameter_name = 'owner_count'

    def lookups(self, request, model_admin):
        return (
            ('0', 'No owners'),
            ('1', 'Single owner'),
            ('2+', 'Multiple owners'),
        )

    def queryset(self, request, queryset):
        if self.value() == '0':
            return queryset.annotate(num_owners=models.Count('owners')).filter(num_owners=0)
        elif self.value() == '1':
            return queryset.annotate(num_owners=models.Count('owners')).filter(num_owners=1)
        elif self.value() == '2+':
            return queryset.annotate(num_owners=models.Count('owners')).filter(num_owners__gte=2)
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
    list_display = ('link_id_short', 'name_display', 'curtain_type', 'created', 'last_access_display', 'owner_list', 'enable', 'permanent_badge', 'expired_status', 'encrypted', 'quick_actions')
    list_filter = ('curtain_type', 'enable', 'permanent', 'encrypted', ExpiredStatusFilter, ExpiringSoonFilter, LastAccessFilter, OwnerCountFilter, MultipleIDsFilter, 'created', 'updated')
    search_fields = ('link_id', 'name', 'description', 'owners__username')
    readonly_fields = ('created', 'updated', 'link_id', 'expired_status', 'last_access_display')
    autocomplete_fields = ('owners',)
    date_hierarchy = 'created'
    list_per_page = 20
    list_editable = ('enable',)
    actions = [
        'batch_add_owner', 'batch_add_to_collection',
        'enable_selected', 'disable_selected',
        'make_permanent', 'extend_expiry_3_months', 'extend_expiry_6_months',
        'delete_expired_sessions', 'export_to_csv',
        'duplicate_curtain',
    ]

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
        owners = obj.owners.all()[:3]
        if owners:
            links = []
            for owner in owners:
                url = reverse('admin:auth_user_change', args=[owner.id])
                links.append(f'<a href="{url}">{owner.username}</a>')
            result = ', '.join(links)
            if obj.owners.count() > 3:
                result += f' (+{obj.owners.count() - 3})'
            return format_html(result)
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

    def batch_add_owner(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return redirect(f"{reverse('admin:curtain_curtain_batch_add_owner')}?ids={','.join(str(pk) for pk in selected)}")
    batch_add_owner.short_description = "Add owner to selected curtains"

    def batch_add_owner_view(self, request):
        ids = request.GET.get('ids', '').split(',')
        curtains = Curtain.objects.filter(pk__in=ids)

        if request.method == 'POST':
            form = BatchAddOwnerForm(request.POST)
            if form.is_valid():
                user = form.cleaned_data['user']
                count = 0
                for curtain in curtains:
                    if user not in curtain.owners.all():
                        curtain.owners.add(user)
                        count += 1
                self.message_user(request, f"Added {user.username} as owner to {count} curtain(s).")
                return redirect('admin:curtain_curtain_changelist')
        else:
            form = BatchAddOwnerForm()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Batch Add Owner',
            'form': form,
            'curtains': curtains,
            'opts': self.model._meta,
        }
        return render(request, 'admin/curtain/batch_add_owner.html', context)

    def batch_add_to_collection(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return redirect(f"{reverse('admin:curtain_curtain_batch_add_to_collection')}?ids={','.join(str(pk) for pk in selected)}")
    batch_add_to_collection.short_description = "Add selected curtains to collection"

    def batch_add_to_collection_view(self, request):
        ids = request.GET.get('ids', '').split(',')
        curtains = Curtain.objects.filter(pk__in=ids)

        if request.method == 'POST':
            form = BatchAddToCollectionForm(request.POST)
            if form.is_valid():
                collection = form.cleaned_data['collection']
                count = 0
                for curtain in curtains:
                    if curtain not in collection.curtains.all():
                        collection.curtains.add(curtain)
                        count += 1
                self.message_user(request, f"Added {count} curtain(s) to collection '{collection.name}'.")
                return redirect('admin:curtain_curtain_changelist')
        else:
            form = BatchAddToCollectionForm()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Batch Add to Collection',
            'form': form,
            'curtains': curtains,
            'opts': self.model._meta,
        }
        return render(request, 'admin/curtain/batch_add_to_collection.html', context)

    def name_display(self, obj):
        if obj.name:
            return obj.name[:30] + '...' if len(obj.name) > 30 else obj.name
        return '-'
    name_display.short_description = 'Name'

    def permanent_badge(self, obj):
        if obj.permanent:
            return format_html('<span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">Permanent</span>')
        return format_html('<span style="background: #6c757d; color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px;">Temporary</span>')
    permanent_badge.short_description = 'Type'

    def quick_actions(self, obj):
        actions = []
        if not obj.permanent:
            actions.append(f'<a href="{reverse("admin:curtain_curtain_quick_action")}?id={obj.pk}&action=make_permanent" title="Make Permanent" style="margin-right:5px;">&#9733;</a>')
        if obj.enable:
            actions.append(f'<a href="{reverse("admin:curtain_curtain_quick_action")}?id={obj.pk}&action=disable" title="Disable" style="color:red;">&#10007;</a>')
        else:
            actions.append(f'<a href="{reverse("admin:curtain_curtain_quick_action")}?id={obj.pk}&action=enable" title="Enable" style="color:green;">&#10003;</a>')
        return format_html(' '.join(actions))
    quick_actions.short_description = 'Actions'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('batch-add-owner/', self.admin_site.admin_view(self.batch_add_owner_view), name='curtain_curtain_batch_add_owner'),
            path('batch-add-to-collection/', self.admin_site.admin_view(self.batch_add_to_collection_view), name='curtain_curtain_batch_add_to_collection'),
            path('quick-action/', self.admin_site.admin_view(self.quick_action_view), name='curtain_curtain_quick_action'),
            path('export-csv/', self.admin_site.admin_view(self.export_csv_view), name='curtain_curtain_export_csv'),
            path('maintenance/', self.admin_site.admin_view(self.maintenance_view), name='curtain_curtain_maintenance'),
            path('duplicate/', self.admin_site.admin_view(self.duplicate_curtain_view), name='curtain_curtain_duplicate'),
        ]
        return custom_urls + urls

    def quick_action_view(self, request):
        curtain_id = request.GET.get('id')
        action = request.GET.get('action')
        curtain = Curtain.objects.get(pk=curtain_id)

        if action == 'enable':
            curtain.enable = True
            curtain.save()
            self.message_user(request, f"Curtain {curtain.link_id[:8]}... enabled.")
        elif action == 'disable':
            curtain.enable = False
            curtain.save()
            self.message_user(request, f"Curtain {curtain.link_id[:8]}... disabled.")
        elif action == 'make_permanent':
            curtain.permanent = True
            curtain.save()
            self.message_user(request, f"Curtain {curtain.link_id[:8]}... made permanent.")

        return redirect('admin:curtain_curtain_changelist')

    def enable_selected(self, request, queryset):
        count = queryset.update(enable=True)
        self.message_user(request, f"Enabled {count} curtain(s).")
    enable_selected.short_description = "Enable selected curtains"

    def disable_selected(self, request, queryset):
        count = queryset.update(enable=False)
        self.message_user(request, f"Disabled {count} curtain(s).")
    disable_selected.short_description = "Disable selected curtains"

    def make_permanent(self, request, queryset):
        count = queryset.update(permanent=True)
        self.message_user(request, f"Made {count} curtain(s) permanent.")
    make_permanent.short_description = "Make selected curtains permanent"

    def extend_expiry_3_months(self, request, queryset):
        from datetime import timedelta
        count = 0
        for curtain in queryset.filter(permanent=False):
            curtain.expiry_duration = timedelta(days=90)
            curtain.save()
            count += 1
        self.message_user(request, f"Extended expiry to 3 months for {count} curtain(s).")
    extend_expiry_3_months.short_description = "Extend expiry to 3 months"

    def extend_expiry_6_months(self, request, queryset):
        from datetime import timedelta
        count = 0
        for curtain in queryset.filter(permanent=False):
            curtain.expiry_duration = timedelta(days=180)
            curtain.save()
            count += 1
        self.message_user(request, f"Extended expiry to 6 months for {count} curtain(s).")
    extend_expiry_6_months.short_description = "Extend expiry to 6 months"

    def delete_expired_sessions(self, request, queryset):
        count = 0
        for curtain in queryset:
            if curtain.is_expired:
                curtain.delete()
                count += 1
        self.message_user(request, f"Deleted {count} expired curtain(s).")
    delete_expired_sessions.short_description = "Delete expired sessions (from selection)"

    def export_to_csv(self, request, queryset):
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="curtains_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['Link ID', 'Name', 'Type', 'Created', 'Enable', 'Permanent', 'Expired', 'Owners', 'Description'])
        for curtain in queryset:
            owners = ', '.join([o.username for o in curtain.owners.all()])
            writer.writerow([
                curtain.link_id,
                curtain.name,
                curtain.curtain_type,
                curtain.created.strftime('%Y-%m-%d %H:%M:%S'),
                curtain.enable,
                curtain.permanent,
                curtain.is_expired,
                owners,
                curtain.description[:100] if curtain.description else ''
            ])
        return response
    export_to_csv.short_description = "Export selected to CSV"

    def duplicate_curtain(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return redirect(f"{reverse('admin:curtain_curtain_duplicate')}?ids={','.join(str(pk) for pk in selected)}")
    duplicate_curtain.short_description = "Duplicate selected curtains (settings only)"

    def export_csv_view(self, request):
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="all_curtains_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['Link ID', 'Name', 'Type', 'Created', 'Enable', 'Permanent', 'Expired', 'Owners', 'Description'])
        for curtain in Curtain.objects.all().prefetch_related('owners'):
            owners = ', '.join([o.username for o in curtain.owners.all()])
            writer.writerow([
                curtain.link_id,
                curtain.name,
                curtain.curtain_type,
                curtain.created.strftime('%Y-%m-%d %H:%M:%S'),
                curtain.enable,
                curtain.permanent,
                curtain.is_expired,
                owners,
                curtain.description[:100] if curtain.description else ''
            ])
        return response

    def maintenance_view(self, request):
        from datetime import timedelta
        from django.utils import timezone

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'delete_expired':
                count = 0
                for curtain in Curtain.objects.filter(permanent=False):
                    if curtain.is_expired:
                        curtain.delete()
                        count += 1
                self.message_user(request, f"Deleted {count} expired curtain(s).")
            elif action == 'delete_no_access_30':
                threshold = timezone.now() - timedelta(days=30)
                count = 0
                for curtain in Curtain.objects.filter(permanent=False):
                    last_access = curtain.last_access.order_by('-last_access').first()
                    if not last_access or last_access.last_access < threshold:
                        curtain.delete()
                        count += 1
                self.message_user(request, f"Deleted {count} curtain(s) with no access in 30 days.")
            elif action == 'delete_no_access_90':
                threshold = timezone.now() - timedelta(days=90)
                count = 0
                for curtain in Curtain.objects.filter(permanent=False):
                    last_access = curtain.last_access.order_by('-last_access').first()
                    if not last_access or last_access.last_access < threshold:
                        curtain.delete()
                        count += 1
                self.message_user(request, f"Deleted {count} curtain(s) with no access in 90 days.")
            return redirect('admin:curtain_curtain_maintenance')

        total_curtains = Curtain.objects.count()
        expired_count = sum(1 for c in Curtain.objects.filter(permanent=False) if c.is_expired)
        permanent_count = Curtain.objects.filter(permanent=True).count()
        enabled_count = Curtain.objects.filter(enable=True).count()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Curtain Maintenance',
            'opts': self.model._meta,
            'total_curtains': total_curtains,
            'expired_count': expired_count,
            'permanent_count': permanent_count,
            'enabled_count': enabled_count,
        }
        return render(request, 'admin/curtain/maintenance.html', context)

    def duplicate_curtain_view(self, request):
        import uuid
        ids = request.GET.get('ids', '').split(',')
        curtains = Curtain.objects.filter(pk__in=ids)

        if request.method == 'POST':
            new_owner_id = request.POST.get('new_owner')
            copy_owners = request.POST.get('copy_owners') == 'on'
            copy_description = request.POST.get('copy_description') == 'on'

            new_owner = None
            if new_owner_id:
                new_owner = User.objects.get(pk=new_owner_id)

            duplicated = []
            for original in curtains:
                new_curtain = Curtain.objects.create(
                    link_id=str(uuid.uuid4()),
                    name=f"Copy of {original.name}" if original.name else f"Copy of {str(original.link_id)[:8]}",
                    curtain_type=original.curtain_type,
                    description=original.description if copy_description else '',
                    enable=False,
                    permanent=False,
                    encrypted=False,
                    expiry_duration=original.expiry_duration,
                )
                if copy_owners:
                    new_curtain.owners.set(original.owners.all())
                if new_owner and new_owner not in new_curtain.owners.all():
                    new_curtain.owners.add(new_owner)
                duplicated.append(new_curtain)

            self.message_user(request, f"Successfully duplicated {len(duplicated)} curtain(s). Note: Files are not copied - you need to upload new data.")
            return redirect('admin:curtain_curtain_changelist')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Duplicate Curtains',
            'curtains': curtains,
            'users': User.objects.all().order_by('username')[:100],
            'opts': self.model._meta,
        }
        return render(request, 'admin/curtain/duplicate_curtain.html', context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_maintenance_link'] = True
        extra_context['show_export_link'] = True
        return super().changelist_view(request, extra_context=extra_context)


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
    autocomplete_fields = ('user',)

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
    autocomplete_fields = ('user',)
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
    autocomplete_fields = ('user',)

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
    autocomplete_fields = ('curtain',)
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
    autocomplete_fields = ('curtain',)
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
    autocomplete_fields = ('curtain',)
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
    autocomplete_fields = ('curtain',)
    date_hierarchy = 'last_access'
    actions = ['purge_keep_latest', 'purge_older_than_30_days', 'purge_older_than_90_days', 'purge_older_than_365_days']

    def curtain_link(self, obj):
        if obj.curtain:
            return str(obj.curtain.link_id)[:8] + '...'
        return 'N/A'
    curtain_link.short_description = 'Curtain'

    def purge_keep_latest(self, request, queryset):
        from django.db.models import Max
        latest_per_curtain = LastAccess.objects.values('curtain').annotate(latest_id=Max('id')).values_list('latest_id', flat=True)
        count, _ = LastAccess.objects.exclude(id__in=list(latest_per_curtain)).delete()
        self.message_user(request, f"Purged {count} old access record(s), keeping only the latest for each curtain.")
    purge_keep_latest.short_description = "Purge all except latest per curtain"

    def purge_older_than_30_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=30)
        count, _ = LastAccess.objects.filter(last_access__lt=threshold).delete()
        self.message_user(request, f"Purged {count} access record(s) older than 30 days.")
    purge_older_than_30_days.short_description = "Purge records older than 30 days"

    def purge_older_than_90_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=90)
        count, _ = LastAccess.objects.filter(last_access__lt=threshold).delete()
        self.message_user(request, f"Purged {count} access record(s) older than 90 days.")
    purge_older_than_90_days.short_description = "Purge records older than 90 days"

    def purge_older_than_365_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=365)
        count, _ = LastAccess.objects.filter(last_access__lt=threshold).delete()
        self.message_user(request, f"Purged {count} access record(s) older than 1 year.")
    purge_older_than_365_days.short_description = "Purge records older than 1 year"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('purge/', self.admin_site.admin_view(self.purge_view), name='curtain_lastaccess_purge'),
        ]
        return custom_urls + urls

    def purge_view(self, request):
        from datetime import timedelta
        from django.utils import timezone
        from django.db.models import Max, Count

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'purge_keep_latest':
                latest_per_curtain = LastAccess.objects.values('curtain').annotate(latest_id=Max('id')).values_list('latest_id', flat=True)
                count, _ = LastAccess.objects.exclude(id__in=list(latest_per_curtain)).delete()
                self.message_user(request, f"Purged {count} old access record(s), keeping only the latest for each curtain.")
            elif action == 'purge_30':
                threshold = timezone.now() - timedelta(days=30)
                count, _ = LastAccess.objects.filter(last_access__lt=threshold).delete()
                self.message_user(request, f"Purged {count} access record(s) older than 30 days.")
            elif action == 'purge_90':
                threshold = timezone.now() - timedelta(days=90)
                count, _ = LastAccess.objects.filter(last_access__lt=threshold).delete()
                self.message_user(request, f"Purged {count} access record(s) older than 90 days.")
            elif action == 'purge_365':
                threshold = timezone.now() - timedelta(days=365)
                count, _ = LastAccess.objects.filter(last_access__lt=threshold).delete()
                self.message_user(request, f"Purged {count} access record(s) older than 1 year.")
            return redirect('admin:curtain_lastaccess_changelist')

        total_records = LastAccess.objects.count()
        curtains_with_access = LastAccess.objects.values('curtain').distinct().count()
        duplicate_count = total_records - curtains_with_access

        month_ago = timezone.now() - timedelta(days=30)
        quarter_ago = timezone.now() - timedelta(days=90)
        year_ago = timezone.now() - timedelta(days=365)

        older_than_30 = LastAccess.objects.filter(last_access__lt=month_ago).count()
        older_than_90 = LastAccess.objects.filter(last_access__lt=quarter_ago).count()
        older_than_365 = LastAccess.objects.filter(last_access__lt=year_ago).count()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Purge Last Access Records',
            'opts': LastAccess._meta,
            'total_records': total_records,
            'curtains_with_access': curtains_with_access,
            'duplicate_count': duplicate_count,
            'older_than_30': older_than_30,
            'older_than_90': older_than_90,
            'older_than_365': older_than_365,
        }
        return render(request, 'admin/curtain/purge_last_access.html', context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_purge_link'] = True
        return super().changelist_view(request, extra_context=extra_context)

class DataCiteAdmin(admin.ModelAdmin):
    list_display = ('id', 'title_preview', 'user', 'status_badge', 'doi_link', 'curtain_link', 'has_local_file', 'lock', 'created', 'updated')
    list_filter = ('status', 'lock', 'created', 'updated')
    search_fields = ('title', 'doi', 'user__username', 'contact_email', 'curtain__link_id')
    readonly_fields = ('created', 'updated', 'doi', 'local_file', 'local_file_link')
    autocomplete_fields = ('user', 'curtain', 'collection')
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
    autocomplete_fields = ('curtain', 'requested_by', 'reviewed_by')
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
    list_display = ('name', 'owner', 'enable', 'curtain_count', 'enabled_curtain_count', 'created', 'updated')
    list_filter = ('enable', 'created', 'updated')
    search_fields = ('name', 'description', 'owner__username')
    readonly_fields = ('created', 'updated')
    autocomplete_fields = ('curtains', 'owner')
    ordering = ('-updated',)
    actions = ['enable_all_curtains', 'disable_all_curtains', 'enable_collection', 'disable_collection', 'clone_collection']

    fieldsets = (
        ('Collection Information', {
            'fields': ('name', 'description', 'owner', 'enable')
        }),
        ('Curtain Sessions', {
            'fields': ('curtains',),
            'description': 'Use "Manage Curtain Sharing" button below to toggle individual curtain sharing status.'
        }),
        ('Timestamps', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',)
        }),
    )

    def curtain_count(self, obj):
        return obj.curtains.count()
    curtain_count.short_description = 'Total'

    def enabled_curtain_count(self, obj):
        enabled = obj.curtains.filter(enable=True).count()
        total = obj.curtains.count()
        return f"{enabled}/{total}"
    enabled_curtain_count.short_description = 'Enabled'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('owner').prefetch_related('curtains')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:collection_id>/manage-curtains/', self.admin_site.admin_view(self.manage_curtains_view), name='curtain_curtaincollection_manage_curtains'),
            path('clone/', self.admin_site.admin_view(self.clone_collection_view), name='curtain_curtaincollection_clone'),
        ]
        return custom_urls + urls

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_manage_curtains'] = True
        extra_context['collection_id'] = object_id
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def manage_curtains_view(self, request, collection_id):
        collection = CurtainCollection.objects.get(pk=collection_id)
        curtains = collection.curtains.all().order_by('-created')

        if request.method == 'POST':
            curtain_id = request.POST.get('curtain_id')
            action = request.POST.get('action')
            if curtain_id and action:
                curtain = Curtain.objects.get(pk=curtain_id)
                if action == 'enable':
                    curtain.enable = True
                elif action == 'disable':
                    curtain.enable = False
                curtain.save()
                self.message_user(request, f"Curtain {curtain.link_id[:8]}... {'enabled' if curtain.enable else 'disabled'}.")
            return redirect('admin:curtain_curtaincollection_manage_curtains', collection_id=collection_id)

        context = {
            **self.admin_site.each_context(request),
            'title': f'Manage Curtains in "{collection.name}"',
            'collection': collection,
            'curtains': curtains,
            'opts': self.model._meta,
        }
        return render(request, 'admin/curtain/manage_collection_curtains.html', context)

    def enable_all_curtains(self, request, queryset):
        count = 0
        for collection in queryset:
            updated = collection.curtains.update(enable=True)
            count += updated
        self.message_user(request, f"Enabled {count} curtain(s) across {queryset.count()} collection(s).")
    enable_all_curtains.short_description = "Enable all curtains in selected collections"

    def disable_all_curtains(self, request, queryset):
        count = 0
        for collection in queryset:
            updated = collection.curtains.update(enable=False)
            count += updated
        self.message_user(request, f"Disabled {count} curtain(s) across {queryset.count()} collection(s).")
    disable_all_curtains.short_description = "Disable all curtains in selected collections"

    def enable_collection(self, request, queryset):
        count = queryset.update(enable=True)
        self.message_user(request, f"Enabled {count} collection(s).")
    enable_collection.short_description = "Enable selected collections"

    def disable_collection(self, request, queryset):
        count = queryset.update(enable=False)
        self.message_user(request, f"Disabled {count} collection(s).")
    disable_collection.short_description = "Disable selected collections"

    def clone_collection(self, request, queryset):
        selected = queryset.values_list('pk', flat=True)
        return redirect(f"{reverse('admin:curtain_curtaincollection_clone')}?ids={','.join(str(pk) for pk in selected)}")
    clone_collection.short_description = "Clone selected collections"

    def clone_collection_view(self, request):
        ids = request.GET.get('ids', '').split(',')
        collections = CurtainCollection.objects.filter(pk__in=ids)

        if request.method == 'POST':
            new_owner_id = request.POST.get('new_owner')
            copy_owner = request.POST.get('copy_owner') == 'on'
            copy_curtains = request.POST.get('copy_curtains') == 'on'

            new_owner = None
            if new_owner_id:
                new_owner = User.objects.get(pk=new_owner_id)

            cloned = []
            for original in collections:
                new_collection = CurtainCollection.objects.create(
                    name=f"Copy of {original.name}",
                    description=original.description,
                    enable=False,
                    owner=new_owner if new_owner else (original.owner if copy_owner else None),
                )
                if copy_curtains:
                    new_collection.curtains.set(original.curtains.all())
                cloned.append(new_collection)

            self.message_user(request, f"Successfully cloned {len(cloned)} collection(s).")
            return redirect('admin:curtain_curtaincollection_changelist')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Clone Collections',
            'collections': collections,
            'users': User.objects.all().order_by('username')[:100],
            'opts': self.model._meta,
        }
        return render(request, 'admin/curtain/clone_collection.html', context)


class RequestAdmin(admin.ModelAdmin):
    list_display = ('time', 'path', 'method', 'response', 'user', 'ip', 'referer_display')
    list_filter = ('method', 'response', 'is_ajax', 'is_secure', 'time')
    search_fields = ('path', 'ip', 'user__username', 'referer')
    readonly_fields = ('time', 'path', 'method', 'response', 'user', 'ip', 'referer', 'user_agent', 'language', 'is_ajax', 'is_secure')
    date_hierarchy = 'time'
    list_per_page = 50
    ordering = ('-time',)
    actions = ['purge_older_than_7_days', 'purge_older_than_30_days', 'purge_older_than_90_days', 'purge_older_than_365_days', 'purge_all_logs']

    def referer_display(self, obj):
        if obj.referer:
            return obj.referer[:50] + '...' if len(obj.referer) > 50 else obj.referer
        return '-'
    referer_display.short_description = 'Referer'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def purge_older_than_7_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=7)
        count, _ = Request.objects.filter(time__lt=threshold).delete()
        self.message_user(request, f"Purged {count} request log(s) older than 7 days.")
    purge_older_than_7_days.short_description = "Purge logs older than 7 days (all, not just selected)"

    def purge_older_than_30_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=30)
        count, _ = Request.objects.filter(time__lt=threshold).delete()
        self.message_user(request, f"Purged {count} request log(s) older than 30 days.")
    purge_older_than_30_days.short_description = "Purge logs older than 30 days (all, not just selected)"

    def purge_older_than_90_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=90)
        count, _ = Request.objects.filter(time__lt=threshold).delete()
        self.message_user(request, f"Purged {count} request log(s) older than 90 days.")
    purge_older_than_90_days.short_description = "Purge logs older than 90 days (all, not just selected)"

    def purge_older_than_365_days(self, request, queryset):
        from datetime import timedelta
        from django.utils import timezone
        threshold = timezone.now() - timedelta(days=365)
        count, _ = Request.objects.filter(time__lt=threshold).delete()
        self.message_user(request, f"Purged {count} request log(s) older than 1 year.")
    purge_older_than_365_days.short_description = "Purge logs older than 1 year (all, not just selected)"

    def purge_all_logs(self, request, queryset):
        count, _ = Request.objects.all().delete()
        self.message_user(request, f"Purged all {count} request log(s).")
    purge_all_logs.short_description = "Purge ALL request logs"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('purge/', self.admin_site.admin_view(self.purge_view), name='request_request_purge'),
        ]
        return custom_urls + urls

    def purge_view(self, request):
        from datetime import timedelta
        from django.utils import timezone

        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'purge_7':
                threshold = timezone.now() - timedelta(days=7)
                count, _ = Request.objects.filter(time__lt=threshold).delete()
                self.message_user(request, f"Purged {count} request log(s) older than 7 days.")
            elif action == 'purge_30':
                threshold = timezone.now() - timedelta(days=30)
                count, _ = Request.objects.filter(time__lt=threshold).delete()
                self.message_user(request, f"Purged {count} request log(s) older than 30 days.")
            elif action == 'purge_90':
                threshold = timezone.now() - timedelta(days=90)
                count, _ = Request.objects.filter(time__lt=threshold).delete()
                self.message_user(request, f"Purged {count} request log(s) older than 90 days.")
            elif action == 'purge_365':
                threshold = timezone.now() - timedelta(days=365)
                count, _ = Request.objects.filter(time__lt=threshold).delete()
                self.message_user(request, f"Purged {count} request log(s) older than 1 year.")
            elif action == 'purge_all':
                count, _ = Request.objects.all().delete()
                self.message_user(request, f"Purged all {count} request log(s).")
            return redirect('admin:request_request_changelist')

        total_logs = Request.objects.count()
        week_ago = timezone.now() - timedelta(days=7)
        month_ago = timezone.now() - timedelta(days=30)
        quarter_ago = timezone.now() - timedelta(days=90)
        year_ago = timezone.now() - timedelta(days=365)

        older_than_7 = Request.objects.filter(time__lt=week_ago).count()
        older_than_30 = Request.objects.filter(time__lt=month_ago).count()
        older_than_90 = Request.objects.filter(time__lt=quarter_ago).count()
        older_than_365 = Request.objects.filter(time__lt=year_ago).count()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Purge Request Logs',
            'opts': Request._meta,
            'total_logs': total_logs,
            'older_than_7': older_than_7,
            'older_than_30': older_than_30,
            'older_than_90': older_than_90,
            'older_than_365': older_than_365,
        }
        return render(request, 'admin/request/purge_logs.html', context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_purge_link'] = True
        return super().changelist_view(request, extra_context=extra_context)


admin.site.unregister(Request)
admin.site.register(Request, RequestAdmin)

