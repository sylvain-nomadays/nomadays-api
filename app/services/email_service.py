"""
SendGrid email service for Nomadays.

Handles sending transactional emails (pre-booking requests, notifications, etc.)
via the SendGrid API. Falls back to logging in development when no API key is set.
"""

import logging
from datetime import date
from typing import Any

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service using SendGrid.

    If sendgrid_api_key is empty, emails are logged but not sent,
    allowing local development without a real API key.
    """

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.sendgrid_api_key
        self.from_email = settings.sendgrid_from_email
        self.from_name = settings.sendgrid_from_name
        self._client = None

    @property
    def client(self) -> SendGridAPIClient | None:
        """Lazy-init SendGrid client."""
        if self._client is None and self.api_key:
            self._client = SendGridAPIClient(api_key=self.api_key)
        return self._client

    @property
    def is_configured(self) -> bool:
        """Check whether a real API key is configured."""
        return bool(self.api_key)

    # ------------------------------------------------------------------
    # Generic sender
    # ------------------------------------------------------------------

    def send_generic(self, to: str, subject: str, html_content: str) -> bool:
        """
        Send a generic email.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html_content: HTML body of the email.

        Returns:
            True if the email was sent (or simulated) successfully.
        """
        if not self.is_configured:
            logger.warning(
                "SendGrid API key not configured — simulating email send. "
                "To=%s Subject=%s",
                to,
                subject,
            )
            return True

        message = Mail(
            from_email=Email(self.from_email, self.from_name),
            to_emails=To(to),
            subject=subject,
            html_content=HtmlContent(html_content),
        )

        try:
            response = self.client.send(message)
            logger.info(
                "Email sent via SendGrid. to=%s subject=%s status=%s",
                to,
                subject,
                response.status_code,
            )
            return True
        except Exception as exc:
            logger.error(
                "Failed to send email via SendGrid. to=%s subject=%s error=%s",
                to,
                subject,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Pre-booking request email
    # ------------------------------------------------------------------

    def send_pre_booking_request(
        self,
        booking: Any,
        supplier: Any,
        trip: Any,
    ) -> bool:
        """
        Send a pre-booking request email to a supplier.

        Args:
            booking: Pre-booking object with fields such as description,
                     start_date, end_date, pax_count, guest_names,
                     room_config, supplier_response_note.
            supplier: Supplier object with email, name fields.
            trip: Trip object with reference, dmc_contact_name,
                  dmc_contact_email, dmc_contact_phone.

        Returns:
            True if the email was sent (or simulated) successfully.
        """
        to_email = getattr(supplier, "reservation_email", None) or getattr(supplier, "contact_email", None)
        if not to_email:
            logger.warning(
                "Supplier %s has no email address — cannot send pre-booking request.",
                getattr(supplier, "name", "unknown"),
            )
            return False

        # Format dates
        start_date = _format_date(getattr(booking, "service_date_start", None))
        end_date = _format_date(getattr(booking, "service_date_end", None))

        subject = (
            f"Booking Request — {booking.description} — "
            f"{start_date} to {end_date}"
        )

        html_content = _build_pre_booking_html(
            booking=booking,
            supplier=supplier,
            trip=trip,
            start_date=start_date,
            end_date=end_date,
        )

        return self.send_generic(to_email, subject, html_content)

    # ------------------------------------------------------------------
    # Trip proposal email (sent to client)
    # ------------------------------------------------------------------

    def send_trip_proposal(
        self,
        trip: Any,
        dossier: Any,
        client_email: str,
        client_name: str,
        cotations: list | None = None,
        days_summary: list | None = None,
        hero_photo_url: str | None = None,
        portal_url: str | None = None,
        advisor_name: str | None = None,
        advisor_photo_url: str | None = None,
    ) -> bool:
        """
        Send a trip proposal email to the client.

        Args:
            trip: Trip object with name, duration_days, destination_country,
                  start_date, end_date, default_currency, etc.
            dossier: Dossier object with reference.
            client_email: Client email address.
            client_name: Client display name.
            cotations: List of cotation summaries [{name, price_label, price_per_person, total_price}].
            days_summary: List of day summaries [{day_number, title}].
            hero_photo_url: URL of the hero photo for the trip.
            portal_url: URL to view the proposal in client portal.
            advisor_name: Name of the travel advisor.
            advisor_photo_url: Photo URL of the advisor.

        Returns:
            True if the email was sent (or simulated) successfully.
        """
        if not client_email:
            logger.warning(
                "No client email for dossier %s — cannot send trip proposal.",
                getattr(dossier, "reference", "unknown"),
            )
            return False

        trip_name = getattr(trip, "name", "Circuit")
        subject = f"Nouvelle proposition de circuit — {trip_name}"

        html_content = _build_trip_proposal_html(
            trip=trip,
            dossier=dossier,
            client_name=client_name,
            cotations=cotations or [],
            days_summary=days_summary or [],
            hero_photo_url=hero_photo_url,
            portal_url=portal_url,
            advisor_name=advisor_name,
            advisor_photo_url=advisor_photo_url,
        )

        return self.send_generic(client_email, subject, html_content)

    # ------------------------------------------------------------------
    # Pre-booking cancellation email
    # ------------------------------------------------------------------

    def send_pre_booking_cancellation(
        self,
        booking: Any,
        supplier: Any,
        trip: Any,
    ) -> bool:
        """
        Send a cancellation email to the supplier for a previously
        requested pre-booking.

        Args:
            booking: Booking object with description, dates, pax info.
            supplier: Supplier object with email and name.
            trip: Trip object with reference and DMC contact info.

        Returns:
            True if the email was sent (or simulated) successfully.
        """
        to_email = getattr(supplier, "reservation_email", None) or getattr(supplier, "contact_email", None)
        if not to_email:
            logger.warning(
                "Supplier %s has no email address — cannot send cancellation.",
                getattr(supplier, "name", "unknown"),
            )
            return False

        # Format dates
        start_date = _format_date(getattr(booking, "service_date_start", None))
        end_date = _format_date(getattr(booking, "service_date_end", None))

        subject = (
            f"Booking Cancellation — {booking.description} — "
            f"{start_date} to {end_date}"
        )

        html_content = _build_cancellation_html(
            booking=booking,
            supplier=supplier,
            trip=trip,
            start_date=start_date,
            end_date=end_date,
        )

        return self.send_generic(to_email, subject, html_content)


# ======================================================================
# Private helpers
# ======================================================================


def _format_date(value: Any) -> str:
    """Return a human-readable date string (DD/MM/YYYY)."""
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str):
        return value
    return str(value) if value else ""


def _build_pre_booking_html(
    booking: Any,
    supplier: Any,
    trip: Any,
    start_date: str,
    end_date: str,
) -> str:
    """Build the HTML body for a pre-booking request email."""

    # Optional sections
    guest_names_section = ""
    if getattr(booking, "guest_names", None):
        guest_names_section = f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;">
                Guest Names
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
                {_escape(booking.guest_names)}
            </td>
        </tr>"""

    room_config_section = ""
    if getattr(booking, "room_config", None):
        room_config_section = f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;">
                Room Configuration
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
                {_escape(booking.room_config)}
            </td>
        </tr>"""

    supplier_note_section = ""
    if getattr(booking, "supplier_response_note", None):
        supplier_note_section = f"""
        <div style="margin-top:20px;padding:12px 16px;background:#FDF5F2;border-left:4px solid #DD9371;border-radius:4px;">
            <strong style="color:#C97A56;">Note:</strong>
            <p style="margin:4px 0 0;color:#525252;">{_escape(booking.supplier_response_note)}</p>
        </div>"""

    # DMC contact info
    dmc_contact_name = getattr(trip, "dmc_contact_name", None) or ""
    dmc_contact_email = getattr(trip, "dmc_contact_email", None) or ""
    dmc_contact_phone = getattr(trip, "dmc_contact_phone", None) or ""

    contact_parts = []
    if dmc_contact_name:
        contact_parts.append(f"<strong>{_escape(dmc_contact_name)}</strong>")
    if dmc_contact_email:
        contact_parts.append(f'<a href="mailto:{_escape(dmc_contact_email)}" style="color:#0FB6BC;">{_escape(dmc_contact_email)}</a>')
    if dmc_contact_phone:
        contact_parts.append(_escape(dmc_contact_phone))

    contact_html = "<br>".join(contact_parts) if contact_parts else "—"

    pax_count = getattr(booking, "pax_count", None) or "—"
    trip_ref = getattr(trip, "reference", None) or ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:'Source Sans 3',Arial,sans-serif;background:#FAFAFA;">
  <div style="max-width:600px;margin:24px auto;background:#FFFFFF;border-radius:8px;border:1px solid #E5E5E5;overflow:hidden;">

    <!-- Header -->
    <div style="background:#0FB6BC;padding:24px 32px;">
      <h1 style="margin:0;color:#FFFFFF;font-family:'Nunito',Arial,sans-serif;font-size:20px;font-weight:700;">
        Booking Request
      </h1>
      {f'<p style="margin:6px 0 0;color:#CCF3F5;font-size:14px;">Ref. {_escape(trip_ref)}</p>' if trip_ref else ''}
    </div>

    <!-- Body -->
    <div style="padding:24px 32px;">
      <p style="color:#525252;font-size:15px;margin:0 0 16px;">
        Dear Sir/Madam,<br>
        We would like to request the following booking:
      </p>

      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;width:40%;">
            Service
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
            {_escape(booking.description)}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;">
            Dates
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
            {_escape(start_date)} &mdash; {_escape(end_date)}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;">
            Number of Guests
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
            {pax_count}
          </td>
        </tr>
        {guest_names_section}
        {room_config_section}
      </table>

      {supplier_note_section}

      <!-- Contact -->
      <div style="margin-top:28px;padding-top:16px;border-top:1px solid #E5E5E5;">
        <p style="color:#525252;font-size:13px;margin:0 0 6px;">
          For any questions, please contact:
        </p>
        <p style="color:#171717;font-size:14px;margin:0;line-height:1.6;">
          {contact_html}
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#F5F5F5;padding:16px 32px;text-align:center;">
      <p style="margin:0;color:#A3A3A3;font-size:12px;">
        This email was sent automatically by the Nomadays platform.
      </p>
    </div>

  </div>
</body>
</html>"""


def _build_cancellation_html(
    booking: Any,
    supplier: Any,
    trip: Any,
    start_date: str,
    end_date: str,
) -> str:
    """Build the HTML body for a pre-booking cancellation email."""

    # Cancellation note (reason)
    cancellation_note_section = ""
    if getattr(booking, "supplier_response_note", None):
        cancellation_note_section = f"""
        <div style="margin-top:20px;padding:12px 16px;background:#FDF5F2;border-left:4px solid #DD9371;border-radius:4px;">
            <strong style="color:#C97A56;">Reason:</strong>
            <p style="margin:4px 0 0;color:#525252;">{_escape(booking.supplier_response_note)}</p>
        </div>"""

    # DMC contact info
    dmc_contact_name = getattr(trip, "dmc_contact_name", None) or ""
    dmc_contact_email = getattr(trip, "dmc_contact_email", None) or ""
    dmc_contact_phone = getattr(trip, "dmc_contact_phone", None) or ""

    contact_parts = []
    if dmc_contact_name:
        contact_parts.append(f"<strong>{_escape(dmc_contact_name)}</strong>")
    if dmc_contact_email:
        contact_parts.append(f'<a href="mailto:{_escape(dmc_contact_email)}" style="color:#0FB6BC;">{_escape(dmc_contact_email)}</a>')
    if dmc_contact_phone:
        contact_parts.append(_escape(dmc_contact_phone))

    contact_html = "<br>".join(contact_parts) if contact_parts else "—"

    pax_count = getattr(booking, "pax_count", None) or "—"
    trip_ref = getattr(trip, "reference", None) or ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:'Source Sans 3',Arial,sans-serif;background:#FAFAFA;">
  <div style="max-width:600px;margin:24px auto;background:#FFFFFF;border-radius:8px;border:1px solid #E5E5E5;overflow:hidden;">

    <!-- Header -->
    <div style="background:#DC2626;padding:24px 32px;">
      <h1 style="margin:0;color:#FFFFFF;font-family:'Nunito',Arial,sans-serif;font-size:20px;font-weight:700;">
        Booking Cancellation
      </h1>
      {f'<p style="margin:6px 0 0;color:#FECACA;font-size:14px;">Ref. {_escape(trip_ref)}</p>' if trip_ref else ''}
    </div>

    <!-- Body -->
    <div style="padding:24px 32px;">
      <p style="color:#525252;font-size:15px;margin:0 0 16px;">
        Dear Sir/Madam,<br>
        We would like to cancel the following booking:
      </p>

      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;width:40%;">
            Service
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
            {_escape(booking.description)}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;">
            Dates
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
            {_escape(start_date)} &mdash; {_escape(end_date)}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#525252;font-weight:600;">
            Number of Guests
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#171717;">
            {pax_count}
          </td>
        </tr>
      </table>

      {cancellation_note_section}

      <!-- Contact -->
      <div style="margin-top:28px;padding-top:16px;border-top:1px solid #E5E5E5;">
        <p style="color:#525252;font-size:13px;margin:0 0 6px;">
          For any questions, please contact:
        </p>
        <p style="color:#171717;font-size:14px;margin:0;line-height:1.6;">
          {contact_html}
        </p>
      </div>
    </div>

    <!-- Footer -->
    <div style="background:#F5F5F5;padding:16px 32px;text-align:center;">
      <p style="margin:0;color:#A3A3A3;font-size:12px;">
        This email was sent automatically by the Nomadays platform.
      </p>
    </div>

  </div>
</body>
</html>"""


def _build_trip_proposal_html(
    trip: Any,
    dossier: Any,
    client_name: str,
    cotations: list,
    days_summary: list,
    hero_photo_url: str | None = None,
    portal_url: str | None = None,
    advisor_name: str | None = None,
    advisor_photo_url: str | None = None,
) -> str:
    """Build the HTML body for a trip proposal email sent to the client.

    Layout matches the Nomadays existing email style:
    - Header: "Nouvelle proposition de circuit"
    - Greeting + intro
    - CTA button
    - Hero photo
    - Trip name + client name
    - Trip details (dates, duration, pricing)
    - Portal benefits section
    - Advisor sign-off with photo
    """

    trip_name = _escape(getattr(trip, "name", "Votre voyage"))
    duration = getattr(trip, "duration_days", 0)
    destination = _escape(getattr(trip, "destination_country", "") or "")
    dossier_ref = _escape(getattr(dossier, "reference", ""))

    # Format dates
    start_date_raw = getattr(trip, "start_date", None)
    end_date_raw = getattr(trip, "end_date", None)
    start_date = _format_date(start_date_raw)
    end_date = _format_date(end_date_raw)

    # Duration text
    duration_text = ""
    if duration and duration > 0:
        nights = duration - 1 if duration > 1 else 0
        duration_text = f"{duration} jours / {nights} nuits" if nights > 0 else f"{duration} jour"

    # Hero photo section (below CTA)
    hero_section = ""
    if hero_photo_url:
        hero_section = f"""
      <div style="margin-top:24px;border-radius:8px;overflow:hidden;">
        <img src="{_escape(hero_photo_url)}" alt="{trip_name}"
             style="width:100%;height:auto;display:block;object-fit:cover;" />
      </div>"""

    # Pricing info from cotations
    price_per_person = ""
    total_price = ""
    if cotations:
        first_cot = cotations[0]
        pp = first_cot.get("price_per_person") or first_cot.get("price_label", "")
        if pp:
            price_per_person = _escape(str(pp))
        tp = first_cot.get("total_price", "")
        if tp:
            total_price = _escape(str(tp))

    # Trip details table rows
    details_rows = ""
    if start_date and end_date:
        details_rows += f"""
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;font-size:14px;width:45%;">
              Date de départ
            </td>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#171717;font-size:14px;font-weight:600;">
              {start_date}
            </td>
          </tr>
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;font-size:14px;">
              Date de retour
            </td>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#171717;font-size:14px;font-weight:600;">
              {end_date}
            </td>
          </tr>"""
    if duration_text:
        details_rows += f"""
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;font-size:14px;">
              Durée
            </td>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#171717;font-size:14px;font-weight:600;">
              {duration_text}
            </td>
          </tr>"""

    # Flight note
    details_rows += """
          <tr>
            <td colspan="2" style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#DD9371;font-size:13px;font-style:italic;">
              ✈ Vol international non inclus
            </td>
          </tr>"""

    if price_per_person:
        details_rows += f"""
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;font-size:14px;">
              Prix par personne
            </td>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#0FB6BC;font-size:18px;font-weight:700;">
              {price_per_person}
            </td>
          </tr>"""
    if total_price:
        details_rows += f"""
          <tr>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#737373;font-size:14px;">
              Prix total
            </td>
            <td style="padding:10px 16px;border-bottom:1px solid #F0F0F0;color:#171717;font-size:16px;font-weight:700;">
              {total_price}
            </td>
          </tr>"""

    # CTA button
    cta_url = portal_url or "#"
    cta_section = f"""
      <div style="margin-top:28px;text-align:center;">
        <a href="{_escape(cta_url)}"
           style="display:inline-block;background:#0FB6BC;color:#FFFFFF;text-decoration:none;padding:16px 40px;border-radius:6px;font-weight:700;font-size:15px;font-family:'Nunito',Arial,sans-serif;">
          Cliquez ici pour voir les détails du voyage
        </a>
      </div>"""

    # Portal benefits section
    benefits_section = """
      <div style="margin-top:32px;padding:20px 24px;background:#F8FFFE;border:1px solid #CCF3F5;border-radius:8px;">
        <h3 style="margin:0 0 12px;color:#0FB6BC;font-family:'Nunito',Arial,sans-serif;font-size:15px;font-weight:700;">
          Votre espace client personnel
        </h3>
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="padding:4px 0;color:#525252;font-size:13px;line-height:1.5;">
              ✓ Consultez le détail jour par jour de votre programme
            </td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#525252;font-size:13px;line-height:1.5;">
              ✓ Visualisez le tarif détaillé et les options
            </td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#525252;font-size:13px;line-height:1.5;">
              ✓ Échangez directement avec votre conseiller
            </td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#525252;font-size:13px;line-height:1.5;">
              ✓ Demandez des modifications à tout moment
            </td>
          </tr>
        </table>
      </div>"""

    # Advisor sign-off
    advisor_display = _escape(advisor_name) if advisor_name else "L'équipe Nomadays"
    advisor_photo_section = ""
    if advisor_photo_url:
        advisor_photo_section = f"""
            <img src="{_escape(advisor_photo_url)}" alt="{advisor_display}"
                 style="width:56px;height:56px;border-radius:50%;object-fit:cover;margin-right:14px;" />"""

    advisor_section = f"""
      <div style="margin-top:32px;padding-top:20px;border-top:1px solid #E5E5E5;">
        <div style="display:flex;align-items:center;">
          {advisor_photo_section}
          <div>
            <p style="margin:0;color:#171717;font-size:14px;font-weight:600;">
              {advisor_display}
            </p>
            <p style="margin:2px 0 0;color:#737373;font-size:13px;">
              Votre conseiller voyage
            </p>
          </div>
        </div>
        <p style="margin:12px 0 0;color:#525252;font-size:14px;line-height:1.6;">
          Je reste à votre entière disposition pour toute question ou modification.
          N'hésitez pas à me contacter !
        </p>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;font-family:'Source Sans 3',Arial,sans-serif;background:#FAFAFA;">
  <div style="max-width:600px;margin:24px auto;background:#FFFFFF;border-radius:8px;border:1px solid #E5E5E5;overflow:hidden;">

    <!-- Header -->
    <div style="background:#0FB6BC;padding:24px 32px;text-align:center;">
      <h1 style="margin:0;color:#FFFFFF;font-family:'Nunito',Arial,sans-serif;font-size:22px;font-weight:700;">
        Nouvelle proposition de circuit
      </h1>
    </div>

    <!-- Body -->
    <div style="padding:28px 32px;">
      <p style="color:#525252;font-size:15px;margin:0 0 8px;line-height:1.6;">
        Bonjour {_escape(client_name)},
      </p>
      <p style="color:#525252;font-size:15px;margin:0 0 4px;line-height:1.6;">
        Nous avons le plaisir de vous présenter une nouvelle proposition de voyage.
      </p>

      {cta_section}
      {hero_section}

      <!-- Trip name & client -->
      <div style="margin-top:24px;">
        <h2 style="margin:0;color:#171717;font-family:'Nunito',Arial,sans-serif;font-size:20px;font-weight:700;">
          {trip_name}
        </h2>
        <p style="margin:4px 0 0;color:#737373;font-size:14px;">
          pour {_escape(client_name)}{f' — {destination}' if destination else ''}
        </p>
        {f'<p style="margin:2px 0 0;color:#A3A3A3;font-size:12px;">Réf. {dossier_ref}</p>' if dossier_ref else ''}
      </div>

      <!-- Trip details table -->
      <div style="margin-top:20px;">
        <table style="width:100%;border-collapse:collapse;border:1px solid #F0F0F0;border-radius:6px;">
          {details_rows}
        </table>
      </div>

      {benefits_section}
      {advisor_section}
    </div>

    <!-- Footer -->
    <div style="background:#F5F5F5;padding:16px 32px;text-align:center;">
      <p style="margin:0;color:#A3A3A3;font-size:12px;">
        Cet email a été envoyé automatiquement par la plateforme Nomadays.
      </p>
    </div>

  </div>
</body>
</html>"""


def _escape(value: Any) -> str:
    """Minimal HTML escape for user-provided values."""
    if value is None:
        return ""
    s = str(value)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
