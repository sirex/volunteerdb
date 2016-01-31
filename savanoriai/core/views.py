from itsdangerous import URLSafeSerializer

from django.shortcuts import render, redirect, get_object_or_404
from django.http import Http404, JsonResponse
from django.core.urlresolvers import reverse
from django.db import transaction, connection
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings

from allauth.account.forms import ChangePasswordForm
from allauth.account.decorators import verified_email_required
from allauth.account.adapter import get_adapter

from savanoriai.core.models import Volunteer, Organisation, VolunteerCampaign
from savanoriai.core.forms import VolunteerProfileForm, OrganisationProfileForm, VolunteerFilterForm
from savanoriai.core.services import get_active_campaign_or_404, log_user_in, get_volunteer_status


def index(request):
    return render(request, 'base.html', {})


@verified_email_required()
def organisation_profile(request):
    try:
        organisation = request.user.organisation
    except Organisation.DoesNotExist:
        raise Http404()

    action = request.POST.get('action') if request.method == 'POST' else None

    if action == 'update_profile':
        profile_form = OrganisationProfileForm(request, request.POST, instance=organisation)
        if profile_form.is_valid():
            profile_form.update_profile(request, request.user, organisation)
            return redirect(reverse('organisation_profile'))
    else:
        profile_form = OrganisationProfileForm(request, instance=organisation)

    if action == 'change_password':
        password_form = ChangePasswordForm(organisation.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            return redirect(reverse('organisation_profile'))
    else:
        password_form = ChangePasswordForm(organisation.user)

    return render(request, 'organisations/profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'current_menu_item': 'organisation:profile',
    })


@verified_email_required()
def volunteer_profile(request):
    try:
        volunteer = request.user.volunteer
    except Volunteer.DoesNotExist:
        raise Http404()

    action = request.POST.get('action') if request.method == 'POST' else None

    if action == 'update_profile':
        profile_form = VolunteerProfileForm(request, request.POST, instance=volunteer)
        if profile_form.is_valid():
            profile_form.update_profile(request, request.user, volunteer)
            return redirect(reverse('volunteer_profile'))
    else:
        profile_form = VolunteerProfileForm(request, instance=volunteer)

    if action == 'change_password':
        password_form = ChangePasswordForm(volunteer.user, request.POST)
        if password_form.is_valid():
            password_form.save()
            return redirect(reverse('volunteer_profile'))
    else:
        password_form = ChangePasswordForm(volunteer.user)

    return render(request, 'volunteers/profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'current_menu_item': 'volunteer:profile',
    })


@verified_email_required()
def volunteers_list(request):
    filter_form = VolunteerFilterForm(request.GET)

    qs = Volunteer.objects.all()

    if filter_form.is_valid():
        cld = filter_form.cleaned_data

        if cld['places']:
            qs = qs.filter(places__id__in=[x.pk for x in cld['places']])

        if cld['shifts']:
            qs = qs.filter(shift__id__in=[x.pk for x in cld['shifts']])

    qs = (
        qs.
        distinct().
        select_related('user').
        prefetch_related('shift', 'places').
        order_by('user__first_name', 'user__last_name', 'id')
    )

    rows_per_page = 25
    paginator = Paginator(qs, rows_per_page)

    try:
        volunteers = paginator.page(request.GET.get('page'))
    except PageNotAnInteger:
        volunteers = paginator.page(1)
    except EmptyPage:
        volunteers = paginator.page(paginator.num_pages)

    return render(request, 'organisations/volunteers_list.html', {
        'filter': filter_form,
        'volunteers': volunteers,
        'current_menu_item': 'organisation:volunteers',
    })


@verified_email_required()
def toggle_choice(request):
    campaign = get_active_campaign_or_404()
    volunteer = get_object_or_404(Volunteer, pk=request.POST.get('volunteer_id'))

    with transaction.atomic():
        cursor = connection.cursor()
        cursor.execute('LOCK TABLE %s' % VolunteerCampaign._meta.db_table)

        created = False

        try:
            obj = VolunteerCampaign.objects.get(
                Q(accepted__isnull=True) | Q(accepted=True),
                campaign=campaign, volunteer=volunteer,
            )
        except VolunteerCampaign.DoesNotExist:
            obj, created = VolunteerCampaign.objects.get_or_create(
                campaign=campaign, volunteer=volunteer,
                organisation=request.user.organisation,
            )

        if created:
            serializer = URLSafeSerializer(settings.SECRET_KEY)
            get_adapter().send_mail('emails/volunteer_invitation', volunteer.user.email, {
                'organisation': request.user.organisation,
                'confirm_invite_url': reverse('confirm_invite', args=[serializer.dumps(obj.pk)]),
            })

    state, label = get_volunteer_status(obj, request.user.organisation)

    return JsonResponse({
        'state': state,
        'label': label,
    })


def confirm_invite(request, volunteer_campaign_id):
    serializer = URLSafeSerializer(settings.SECRET_KEY)
    volunteer_campaign_id = serializer.loads(volunteer_campaign_id)
    volunteer_campaign = get_object_or_404(VolunteerCampaign, pk=volunteer_campaign_id)

    response = log_user_in(request, volunteer_campaign.volunteer.user)
    if response is not None:
        return response

    if request.method == 'POST':
        if request.POST.get('action') == 'accept':
            volunteer_campaign.accepted = True
        else:
            volunteer_campaign.accepted = False
        volunteer_campaign.save()
        return redirect('volunteer_profile')

    return render(request, 'volunteers/confirm.html', {
        'organisation': volunteer_campaign.organisation,
    })
