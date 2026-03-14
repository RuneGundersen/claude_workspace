# Skattefunn-søknad – ISPAS-prosjekt
## Metallisering av 3D-printede strukturer for mikrobølgeteknologi

---

## 1. Prosjekttittel
**Additiv produksjon og metallisering av 3D-printede strukturer for spesialtilpassede waveguideantenner og antennefeed**

---

## 2. Prosjektsammendrag

Prosjektet skal utvikle kunnskap og metoder for å produsere lette, spesialtilpassede antennestrukturer ved hjelp av 3D-printing og etterfølgende metallisering. Målet er å erstatte dyre importerte antenner og antennefeed med egenproduserte løsninger som gir høyere ytelse, lavere vekt og bedre tilpasning til selskapets spesifikke bruksområder – herunder dronemontering og aerodynamisk integrering. Prosjektet er av FoU-karakter da det ikke finnes etablerte prosesser for presisjonsmetallisering av 3D-printede strukturer med de toleransekrav som kreves innen waveguideteknologi i mikrobølgeområdet.

---

## 3. Bakgrunn og motivasjon

Selskapet benytter i dag waveguideantenner og antennefeed innkjøpt fra utenlandske leverandører. Dette medfører flere utfordringer:

- **Kostnad:** Spesialiserte mikrobølgekomponenter er kostbare ved innkjøp fra eksternleverandør.
- **Ytelse:** Kommersielt tilgjengelige produkter er sjelden optimalt tilpasset selskapets spesifikke systemkrav, noe som gir redusert systemytelse.
- **Vekt:** Tradisjonelt maskinerte metallkomponenter er tyngre enn hva som er ønskelig for droneapplikasjoner, hvor nyttelastkapasitet er en kritisk begrensning.
- **Geometrisk frihet:** Innkjøpte komponenter gir begrenset mulighet for å tilpasse antennens form og innfesting til farkostens geometri og aerodynamikk.

Ved å beherske 3D-printing og metallisering in-house vil selskapet oppnå kortere utviklingsløp, lavere komponentkostnad og frihet til å designe antenner som er fullstendig integrert i produktets form og funksjon.

---

## 4. FoU-utfordringer og hypoteser

Prosjektet adresserer følgende forsknings- og utviklingsutfordringer:

### 4.1 Dimensjonell presisjon og overflatekvalitet
Waveguidekomponenter opererer i mikrobølgeområdet og krever svært strenge dimensjonstoleranser (typisk < ±0,1 mm) og lav overflateruhetsverdi (Ra). Det er en åpen forskningsspørsmål om tilgjengelige 3D-printere kan levere tilstrekkelig presisjon, og om etterprosessering kan kompensere for eventuelle avvik.

**Hypotese:** Med valg av riktig printteknologi (SLA/resin eller high-res FDM) og eventuell overflatebehandling er det mulig å oppnå tilstrekkelig dimensjonell nøyaktighet for waveguidedrift i aktuelt frekvensområde.

### 4.2 Adhesjon mellom metall og plast
For å oppnå god ledende overflate på en plaststruktur må metallet bindes tilstrekkelig fast til substratet. Det er usikkert hvilken forbehandling (grafitt-spray, sink-impregnering, kjemisk etsing, plasma-aktivering) som gir best adhesjon og lavest elektrisk motstand for aktuelle plastmaterialer (PLA, ABS, resin).

**Hypotese:** En kombinasjon av overflateaktivering og et tynt ledende forbehandlingslag (grafitt eller sink) etterfulgt av elektrolytisk metallisering (kobber + nikkel) vil gi tilstrekkelig adhesjon og elektrisk ledningsevne.

### 4.3 Elektrisk ytelse
Det er uavklart om metalliseringslaget gir tilstrekkelig lav overflatemotststand (sheet resistance) og dermed akseptabelt lavt innsettingstap for waveguideapplikasjoner i aktuelt frekvensområde.

**Hypotese:** Et metalliseringslag på minimum 5–10 µm kobber etterfølgt av nikkel vil gi overflatesmotstand tilsvarende bulkmetall for frekvenser i aktuelt mikrobølgeområde.

---

## 5. Arbeidsplan og arbeidspakker

### AP1 – Litteraturgjennomgang og teknologikartlegging *(Måned 1–3)*
- Gjennomgang av eksisterende forskning på 3D-printing av RF-strukturer og metallisering av plastsubstrater.
- Kartlegging av tilgjengelige 3D-printteknologier (FDM, SLA, SLS) med hensyn til toleranser og materialegenskaper.
- Kartlegging av metalliseringsmetoder: grafitt-spray, sinkimpregnering, strømløs formetallisering, elektrolytisk belegning.
- **Leveranse:** Teknologirapport med anbefalt prosessvei.

### AP2 – Prosessutvikling: forbehandling og metallisering *(Måned 3–8)*
- Print av testflater og enkle geometrier i utvalgte materialer.
- Eksperimentell testing av ulike forbehandlingsmetoder (grafitt, sink, kjemisk etsing, plasma).
- Etablering av elektrolytisk metalliseringsprosess (kobber/nikkel) tilpasset plastsubstrat.
- Måling av adhesjonsstyrke og overflatesmotstand.
- **Leveranse:** Prosedyre for optimal forbehandling og metallisering.

### AP3 – Design og print av teststrukturer *(Måned 6–12)*
- Elektromagnetisk design av teststrukturer (waveguide-seksjon, horn-antenne, antennefeed) i aktuelt frekvensområde.
- 3D-printing av designede strukturer med valgt teknologi og materiale.
- Metallisering av printede strukturer iht. prosess fra AP2.
- **Leveranse:** Sett med metalliserte teststrukturer klare for RF-måling.

### AP4 – RF-karakterisering og validering *(Måned 10–15)*
- Måling av S-parametere, innsettingstap, refleksjonskoeffisient og strålemønster.
- Sammenligning mot simulerte resultater og ytelse til kommersielle referansekomponenter.
- Identifisering av forbedringsområder og iterasjon av prosess/design.
- **Leveranse:** Målerrapport og validert prosess.

### AP5 – Oppskalering og integrasjon *(Måned 13–18)*
- Produksjon av prototype for integrering i reelt produkt (drone/farkost).
- Vektmåling og sammenligning mot konvensjonelle løsninger.
- Evaluering av aerodynamisk formtilpasning.
- **Leveranse:** Integrert prototypeantenne og sluttrapport.

---

## 6. Forventet resultat og nytteverdi

| Parameter | Mål |
|---|---|
| Vektreduksjon vs. maskinert metall | > 60 % |
| Innsettingstap vs. kommersiell komponent | Tilsvarende eller bedre |
| Kostnad per komponent vs. innkjøp | Reduksjon > 50 % |
| Utviklingstid for ny antennevariant | < 2 uker (fra design til ferdig komponent) |

Prosjektet vil resultere i:
- Intern kompetanse og dokumentert prosess for metallisering av 3D-printede RF-strukturer.
- Redusert avhengighet av utenlandske leverandører.
- Grunnlag for å tilby spesialtilpassede antenneløsninger som ny produktkategori.

---

## 7. Prosjektets FoU-karakter

Prosjektet går utover kjent kunnskap ved at:
- Det ikke finnes etablerte, kommersielt tilgjengelige prosesser for metallisering av 3D-printede strukturer med de toleransekrav som kreves for presisjons-waveguidekomponenter i mikrobølgeområdet.
- Kombinasjonen av additiv produksjon, forbehandling, elektrolytisk metallisering og RF-validering for denne komponentklassen representerer et uavklart teknologisk problemområde.
- Resultatene vil ha overføringsverdi til bransjen og bidra til norsk kompetansebygging innen avansert produksjonsteknologi for forsvarselektronikk og romfart.

---

## 8. Budsjett (estimat)

| Post | Kostnad (NOK) |
|---|---|
| Personalkostnader (ingeniør/forsker, ~1 årsverk) | 1 200 000 |
| 3D-printer (SLA/høyoppløsning) | 150 000 |
| Metalliseringsutstyr og kjemikalier | 200 000 |
| RF-måleutstyr / leiemålinger | 150 000 |
| Materialer og forbruksartikler | 80 000 |
| Reise / kurs / ekstern kompetanse | 70 000 |
| Uforutsett (10 %) | 185 000 |
| **Totalt** | **2 035 000** |

*Skattefunn-fradrag (19 % av godkjent kostnad, maks NOK 8 mill.): ca. NOK 387 000*

---

## 9. Tidsplan

```
Måned:    1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18
AP1       ████████████
AP2                ██████████████████
AP3                         █████████████████
AP4                                     ████████████
AP5                                              ████████████
```

---

## 10. Prosjektorganisering

- **Prosjektleder:** [Navn] – ansvarlig for fremdrift, rapportering og koordinering
- **RF-ingeniør:** Ansvarlig for elektromagnetisk design og RF-måling
- **Produksjonstekniker:** Ansvarlig for 3D-printing og metalliseringsprosess
- **Ekstern kompetanse:** Samarbeid med universitet/SINTEF vurderes for metalliseringsdelen

---

*Søknaden sendes via Norges forskningsråds søknadsportal: [www.forskningsradet.no/skattefunn](https://www.forskningsradet.no/skattefunn)*
