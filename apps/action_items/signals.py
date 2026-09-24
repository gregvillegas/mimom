from django.db.models.signals import pre_save
from django.dispatch import receiver

from apps.action_items.models import ActionItem, ActionItemAssignee
from apps.action_items.services import generate_action_reference


@receiver(pre_save, sender=ActionItem)
def autofill_action_item_reference(sender, instance: ActionItem, **kwargs):
    if not instance.reference:
        generate_action_reference(instance, force=False)


@receiver(pre_save, sender=ActionItemAssignee)
def autofill_assignee_supporting_default(sender, instance: ActionItemAssignee, **kwargs):
    if not instance.is_primary and not instance.is_supporting:
        instance.is_supporting = True
