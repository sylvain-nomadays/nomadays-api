"""CMS snippets — lightweight key-value content store for editable UI texts.

Revision ID: 074_cms_snippets
Revises: 073_booking_logistics_alternative
Create Date: 2025-02-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "074_cms_snippets"
down_revision = "073_booking_logistics_alternative"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cms_snippets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("snippet_key", sa.String(100), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("content_json", JSONB, nullable=False, server_default="'{}'"),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "snippet_key", name="uq_cms_snippets_tenant_key"),
    )

    op.create_index("idx_cms_snippets_tenant_category", "cms_snippets", ["tenant_id", "category"])
    op.create_index("idx_cms_snippets_key", "cms_snippets", ["snippet_key"])
    op.create_index("idx_cms_snippets_tenant_id", "cms_snippets", ["tenant_id"])

    # ── Seed: Global FAQ snippets (tenant_id = NULL) ──────────────────────────
    op.execute("""
        INSERT INTO cms_snippets (tenant_id, snippet_key, category, content_json, metadata_json, sort_order) VALUES
        (NULL, 'faq.programme', 'faq',
         '{"fr": "Rendez-vous dans la section \\"Mes Voyages\\" pour retrouver tous vos projets. Cliquez sur un voyage pour acc\\u00e9der au programme d\\u00e9taill\\u00e9 jour par jour, avec les activit\\u00e9s, h\\u00e9bergements et transports pr\\u00e9vus."}'::jsonb,
         '{"question": {"fr": "Comment consulter mon programme de voyage ?"}, "icon": "Map", "keywords": ["programme", "voyage", "itin\\u00e9raire", "jour", "activit\\u00e9"]}'::jsonb,
         0),

        (NULL, 'faq.contact', 'faq',
         '{"fr": "Vous pouvez envoyer un message \\u00e0 votre h\\u00f4te directement depuis l''onglet \\"Salon de Th\\u00e9\\" de votre voyage, ou depuis la page Salon de Th\\u00e9 accessible via le menu. Votre h\\u00f4te vous r\\u00e9pondra dans les meilleurs d\\u00e9lais."}'::jsonb,
         '{"question": {"fr": "Comment contacter mon h\\u00f4te local ?"}, "icon": "MessageSquare", "keywords": ["h\\u00f4te", "message", "contacter", "\\u00e9crire"]}'::jsonb,
         1),

        (NULL, 'faq.documents', 'faq',
         '{"fr": "Vos documents (programme, vouchers, carnet de voyage) sont accessibles dans l''onglet \\"Documents\\" de votre voyage. Vous pouvez les consulter en ligne ou les t\\u00e9l\\u00e9charger au format PDF."}'::jsonb,
         '{"question": {"fr": "Comment t\\u00e9l\\u00e9charger mes documents de voyage ?"}, "icon": "FileText", "keywords": ["document", "t\\u00e9l\\u00e9charger", "pdf", "voucher"]}'::jsonb,
         2),

        (NULL, 'faq.programme-definitif', 'faq',
         '{"fr": "Votre programme d\\u00e9finitif est g\\u00e9n\\u00e9ralement finalis\\u00e9 2 \\u00e0 3 semaines avant votre date de d\\u00e9part. Votre h\\u00f4te vous informera d\\u00e8s qu''il sera pr\\u00eat."}'::jsonb,
         '{"question": {"fr": "Quand recevrai-je mon programme d\\u00e9finitif ?"}, "icon": "Calendar", "keywords": ["programme", "d\\u00e9finitif", "date", "d\\u00e9part"]}'::jsonb,
         3),

        (NULL, 'faq.modifier-dates', 'faq',
         '{"fr": "Pour toute modification de dates ou d''itin\\u00e9raire, contactez directement votre h\\u00f4te via la messagerie. Il \\u00e9tudiera les possibilit\\u00e9s et vous proposera des alternatives adapt\\u00e9es."}'::jsonb,
         '{"question": {"fr": "Comment modifier mes dates de voyage ?"}, "icon": "Edit3", "keywords": ["modifier", "date", "changer", "itin\\u00e9raire"]}'::jsonb,
         4),

        (NULL, 'faq.urgence', 'faq',
         '{"fr": "En cas d''urgence sur place, contactez imm\\u00e9diatement votre agence locale dont les coordonn\\u00e9es figurent dans vos documents de voyage. Vous pouvez \\u00e9galement joindre votre h\\u00f4te via la messagerie."}'::jsonb,
         '{"question": {"fr": "Que faire en cas d''urgence pendant mon voyage ?"}, "icon": "Phone", "keywords": ["urgence", "aide", "secours", "agence"]}'::jsonb,
         5),

        (NULL, 'faq.ajouter-voyageurs', 'faq',
         '{"fr": "Pour ajouter ou retirer des voyageurs de votre dossier, contactez votre h\\u00f4te via la messagerie. Il mettra \\u00e0 jour la liste des participants."}'::jsonb,
         '{"question": {"fr": "Comment ajouter des voyageurs \\u00e0 mon dossier ?"}, "icon": "Users", "keywords": ["voyageur", "participant", "ajouter", "retirer"]}'::jsonb,
         6),

        (NULL, 'faq.documents-preparer', 'faq',
         '{"fr": "Selon votre destination, vous aurez besoin d''un passeport valide (6 mois minimum apr\\u00e8s le retour), d''un visa \\u00e9ventuel, et de vos vouchers de voyage."}'::jsonb,
         '{"question": {"fr": "Quels documents dois-je pr\\u00e9parer avant le d\\u00e9part ?"}, "icon": "Briefcase", "keywords": ["passeport", "visa", "document", "pr\\u00e9parer"]}'::jsonb,
         7),

        (NULL, 'faq.modifier-itineraire', 'faq',
         '{"fr": "Tant que votre voyage n''est pas encore confirm\\u00e9 et que les r\\u00e9servations ne sont pas finalis\\u00e9es, des modifications sont possibles. Contactez votre h\\u00f4te pour discuter des ajustements."}'::jsonb,
         '{"question": {"fr": "Puis-je modifier l''itin\\u00e9raire de mon voyage ?"}, "icon": "RefreshCw", "keywords": ["modifier", "itin\\u00e9raire", "changer"]}'::jsonb,
         8),

        (NULL, 'faq.paiement', 'faq',
         '{"fr": "Le paiement s''effectue g\\u00e9n\\u00e9ralement en deux fois : un acompte \\u00e0 la confirmation (30 \\u00e0 40%) puis le solde avant le d\\u00e9part."}'::jsonb,
         '{"question": {"fr": "Comment fonctionne le paiement ?"}, "icon": "CreditCard", "keywords": ["paiement", "acompte", "solde", "prix", "facture"]}'::jsonb,
         9);
    """)

    # ── Seed: Global sidebar snippets ──────────────────────────────────────────
    op.execute("""
        INSERT INTO cms_snippets (tenant_id, snippet_key, category, content_json, sort_order) VALUES
        (NULL, 'sidebar.collectif.title', 'sidebar', '{"fr": "Le collectif Nomadays"}'::jsonb, 0),
        (NULL, 'sidebar.collectif.tagline', 'sidebar', '{"fr": "Vos agences locales s''unissent et inventent"}'::jsonb, 1),
        (NULL, 'sidebar.collectif.description', 'sidebar', '{"fr": "Nos h\\u00f4tes locaux vous accueillent comme en famille. Expertise du terrain + garanties d''une agence fran\\u00e7aise."}'::jsonb, 2),
        (NULL, 'sidebar.collectif.phone', 'sidebar', '{"fr": "01 23 45 67 89"}'::jsonb, 3),
        (NULL, 'sidebar.collectif.whatsapp', 'sidebar', '{"fr": "WhatsApp"}'::jsonb, 4),
        (NULL, 'sidebar.collectif.email', 'sidebar', '{"fr": "contact@nomadays.fr"}'::jsonb, 5),
        (NULL, 'sidebar.insurance.title', 'sidebar', '{"fr": "Assurance Chapka"}'::jsonb, 10),
        (NULL, 'sidebar.insurance.subtitle', 'sidebar', '{"fr": "Notre partenaire"}'::jsonb, 11),
        (NULL, 'sidebar.insurance.description', 'sidebar', '{"fr": "Voyagez l''esprit tranquille. Annulation, rapatriement, frais m\\u00e9dicaux..."}'::jsonb, 12),
        (NULL, 'sidebar.insurance.cta_text', 'sidebar', '{"fr": "D\\u00e9couvrir les garanties"}'::jsonb, 13),
        (NULL, 'sidebar.insurance.cta_link', 'sidebar', '{"fr": "#"}'::jsonb, 14),
        (NULL, 'sidebar.ambassador.title', 'sidebar', '{"fr": "Programme Ambassadeur"}'::jsonb, 20),
        (NULL, 'sidebar.ambassador.description', 'sidebar', '{"fr": "Parrainez vos proches et cumulez des r\\u00e9ductions !"}'::jsonb, 21),
        (NULL, 'sidebar.ambassador.cta_text', 'sidebar', '{"fr": "Inviter un proche"}'::jsonb, 22),
        (NULL, 'sidebar.social.instagram', 'sidebar', '{"fr": "#"}'::jsonb, 30),
        (NULL, 'sidebar.social.facebook', 'sidebar', '{"fr": "#"}'::jsonb, 31),
        (NULL, 'sidebar.social.youtube', 'sidebar', '{"fr": "#"}'::jsonb, 32);
    """)

    # ── Seed: Global welcome snippets ──────────────────────────────────────────
    op.execute("""
        INSERT INTO cms_snippets (tenant_id, snippet_key, category, content_json, sort_order) VALUES
        (NULL, 'welcome.title_template', 'welcome', '{"fr": "Bienvenue chez vous, {firstName} \\ud83c\\udfe0"}'::jsonb, 0),
        (NULL, 'welcome.subtitle', 'welcome', '{"fr": "Votre espace voyageur Nomadays"}'::jsonb, 1),
        (NULL, 'welcome.proverb', 'welcome', '{"fr": "Ici, nos h\\u00f4tes locaux vous accueillent comme en famille"}'::jsonb, 2);
    """)

    # ── Seed: Global fidelity snippets ─────────────────────────────────────────
    op.execute("""
        INSERT INTO cms_snippets (tenant_id, snippet_key, category, content_json, metadata_json, sort_order) VALUES
        (NULL, 'fidelity.tier.1', 'fidelity',
         '{"fr": "Explorateur"}'::jsonb,
         '{"emoji": "\\ud83c\\udf0d", "min_trips": 1}'::jsonb, 0),
        (NULL, 'fidelity.tier.2', 'fidelity',
         '{"fr": "Grand Voyageur"}'::jsonb,
         '{"emoji": "\\u2b50", "min_trips": 4}'::jsonb, 1),
        (NULL, 'fidelity.tier.3', 'fidelity',
         '{"fr": "Explorateur du Monde"}'::jsonb,
         '{"emoji": "\\ud83c\\udfc6", "min_trips": 6}'::jsonb, 2);
    """)


def downgrade() -> None:
    op.drop_index("idx_cms_snippets_tenant_id", table_name="cms_snippets")
    op.drop_index("idx_cms_snippets_key", table_name="cms_snippets")
    op.drop_index("idx_cms_snippets_tenant_category", table_name="cms_snippets")
    op.drop_table("cms_snippets")
