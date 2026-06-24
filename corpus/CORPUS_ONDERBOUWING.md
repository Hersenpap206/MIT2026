# Onderbouwing testcorpus T2.1/T2.2 (spraakherkenning)

Dit document legt vast hoe het testcorpus in `bron_T2.1.csv` en `bron_T2.2.csv` tot stand is
gekomen, en wat de wetenschappelijke status van die inhoud is. Bedoeld als bijlage bij de
methodesectie van het haalbaarheidsrapport (WBSO 4.2 / testplan T2.1–T2.2).

## Status van de inhoud

De 20 basiszinnen (en de daarvan afgeleide gefluisterde/emotionele/incomplete varianten) zijn
**door de onderzoeker zelf opgesteld**, niet overgenomen uit een gevalideerde GGZ-specifieke
bron. Er bestaat geen gepubliceerde taxonomie van nachtelijke hulpvragen specifiek voor GGZ-
cliënten die zich onveilig voelen — dat is exact de kennislacune die dit project onderzoekt
(WBSO-onzekerheid 2: "geen bestaande module is getest voor deze combinatie van gebruikerscontext
en veiligheidseisen"). Het corpus is dus een **face-valid, niet-empirisch gevalideerd
testinstrument**, geen wetenschappelijk instrument op zichzelf.

## Indirecte onderbouwing van de categoriestructuur

De keuze om uitingen in te delen naar acuut/fysiek — hulpverzoek — sociaal/emotioneel —
onduidelijk is niet arbitrair: vergelijkbare hoofdcategorieën komen terug in bestaande literatuur
over after-hours-zorgoproepen, zij het niet in een GGZ-nachtzorgcontext:

- Jiang, Y., Gentry, A., & Pusateri, M. E. (2012). A Descriptive, Retrospective Study of
  After-hours Calls in Hospice and Palliative Care. *Journal of Hospice and Palliative Nursing*,
  14(5), 343–350. https://doi.org/10.1097/njh.0b013e31824f1ffa
  Rapporteert symptoombestrijding (25,7%) en aanvraag huisbezoek (15,3%) als grootste
  oproepcategorieën, en citeert eerder werk waarin "emotional support needs" een eigen,
  herkenbare categorie vormt naast medische/medicatie-vragen.
- Kat, M. G., Zuidema, S. U., & van der Ploeg, T. (2008). Reasons for psychiatric consultation
  referrals in Dutch nursing home patients with dementia. *International Journal of Geriatric
  Psychiatry*, 23(10), 1014–1019. https://doi.org/10.1002/gps.2026
  Laat zien dat consultatieredenen in een Nederlandse verpleeghuiscontext systematisch te
  categoriseren zijn (vooral geagiteerd/ontremd gedrag tegenover teruggetrokken gedrag) — dit
  ondersteunt dat een indeling in herkenbare gedrags-/hulpvraagtypen methodologisch gangbaar is.

Geen van beide bronnen is GGZ-nachtzorg-specifiek en geen van beide is gebruikt om de letterlijke
zinnen te formuleren — ze onderbouwen alleen dat de gekozen categorie-indeling aansluit bij
bestaand onderzoek naar soortgelijke zorgcontexten.

## Aanbevolen aanvullende validatiestap: expertbeoordeling tijdens WP2

Om de content-validiteit te verhogen zonder het bestaande urenbudget te overschrijden: gebruik
`expertbeoordeling_template.csv` tijdens de WP2-interviews met zorgprofessionals (zie
projectplan, sectie 2a — marktverkenning/interviews) om de 20 basiszinnen kort te laten
beoordelen op realisme en representativiteit voor de daadwerkelijke GGZ-nachtzorgpraktijk.

Verwerk de ingevulde beoordelingen als `expertbeoordeling_resultaten.csv` (niet meegeleverd in
deze commit — ontstaat tijdens/na de interviews) en vermeld het resultaat in de methodesectie
van het haalbaarheidsrapport als basis voor de content-validiteit van het testcorpus.

## Scope-afspraak (24-06-2026)

Dit corpus en deze onderbouwing gelden uitsluitend voor de GGZ-doelgroep zoals beschreven in de
MIT-aanvraag (MITH26010) en het WBSO-dossier (LOODS-2026-TWO). Een VG-specifiek (verstandelijke
beperking) testcorpus is bewust buiten scope gehouden — VG komt nergens voor in de MIT-aanvraag,
WBSO-stukken of het testplan. Indien een vervolgproject (bijv. EFRO) ook de VG-populatie wil
bedienen, vergt dat een eigen corpusontwerp- en validatietraject; dit document en corpus zijn
daar niet zonder aanpassing op van toepassing.
