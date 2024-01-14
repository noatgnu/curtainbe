from django.contrib import admin

from curtain.models import Curtain, DataFilterList


@admin.register(Curtain)
class CurtainAdmin(admin.ModelAdmin):
    pass


@admin.register(DataFilterList)
class DataFilterListAdmin(admin.ModelAdmin):
    pass