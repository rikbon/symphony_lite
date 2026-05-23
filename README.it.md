# 🎼 Symphony-Lite

> **Un orchestratore minimale per agenti di coding autonomi**, ispirato al framework [Symphony di OpenAI](https://github.com/openai/symphony).

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Agent](https://img.shields.io/badge/Agent-Gemini%20CLI%20%7C%20OpenCode-blueviolet)](https://github.com/google-gemini/gemini-cli)
[![Status](https://img.shields.io/badge/Status-Engineering%20Preview-orange)](https://github.com/openai/symphony)

---

## Indice

- [Cos'è Symphony-Lite](#cosè-symphony-lite)
- [Ispirazione: Symphony di OpenAI](#ispirazione-symphony-di-openai)
- [Filosofia e Differenze rispetto all'originale](#filosofia-e-differenze-rispetto-alloriginale)
- [Come funziona](#come-funziona)
- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Utilizzo](#utilizzo)
- [Riferimento ai parametri CLI](#riferimento-ai-parametri-cli)
- [Il ruolo del file GEMINI.md / WORKFLOW.md](#il-ruolo-del-file-geminimd--workflowmd)
- [Architettura del flusso](#architettura-del-flusso)
- [Cosa Manca (Fuori Scope)](#cosa-manca-fuori-scope)
- [Roadmap](#roadmap)
- [Licenza](#licenza)
- [Link utili](#link-utili)

---

## Cos'è Symphony-Lite

**Symphony-Lite** è un orchestratore Python leggero che automatizza il ciclo di lavoro di un agente AI di coding. Dato un repository Git e una descrizione testuale di un task, questo strumento:

1. **Isola** il lavoro clonando il repo in un workspace dedicato e creando un branch Git univoco.
2. **Delega** il task all'agente CLI scelto (Gemini o OpenCode), passando in modo autonomo tutte le istruzioni operative.
3. **Valida** l'output attendendosi che l'agente verifichi i test prima di dichiarare il task completato.
4. **Prepara l'handoff** committando le modifiche sul branch isolato, pronte per una Pull Request e review umana.

L'obiettivo è passare da *supervisionare* sessioni di coding AI a *gestire il lavoro* ad un livello più alto — esattamente la visione del Symphony originale di OpenAI.

---

## Ispirazione: Symphony di OpenAI

[Symphony](https://github.com/openai/symphony) è un framework open-source pubblicato da OpenAI che ridefinisce il rapporto tra ingegneri e agenti AI. Nasce da un'osservazione pratica interna: **gli sviluppatori incontrano un bottleneck di attenzione umana** quando cercano di gestire più di 3-5 sessioni di coding AI contemporaneamente.

### Il Problema che Symphony risolve

Il modello tradizionale di interazione con un agente è *sincrono e supervisionato*:
- L'ingegnere apre una sessione, scrive il prompt, controlla il progresso, corregge, rilancia.
- Questo non scala: non si possono supervisionare 20 agenti in parallelo.

### La Soluzione di Symphony

Symphony introduce un **piano di controllo** (control plane) che:

- **Integra il tracciatore di ticket** (es. Linear) come fonte di verità per il lavoro da fare.
- **Spawna agenti isolati** per ogni task, ognuno in un proprio workspace.
- **Richiede "Proof of Work"**: l'agente non può dichiarare un task completo senza fornire prove verificabili (CI verde, feedback di code review, video walkthrough).
- **Gestisce automaticamente i fallimenti**: se un agente si blocca o crasha, Symphony lo riavvia.

> *"Ingegneri che gestiscono il lavoro, non le sessioni AI."*
> — filosofia centrale di Symphony

### Componenti chiave dell'originale

| Componente | Descrizione |
|---|---|
| `SPEC.md` | La specifica formale del protocollo Symphony, linguaggio-agnostica |
| Implementazione Elixir | Reference implementation in Elixir/BEAM per alta concorrenza e fault-tolerance |
| Integrazione Linear | Monitoring automatico del project board per acquisire nuovi task |
| Proof of Work | Sistema di verifica: CI status, PR review, analisi della complessità, walkthrough video |
| Harness Engineering | Metodologia per rendere i codebase "machine-legible" e auto-verificabili |

**Linguaggi nel repo originale:** Elixir (95.5%), Python (3%), CSS (1.2%)

---

## Filosofia e Differenze rispetto all'originale

Symphony-Lite ne abbraccia la filosofia ma la semplifica per l'uso individuale e locale:

| Aspetto | Symphony (OpenAI) | Symphony-Lite |
|---|---|---|
| **Complessità** | Sistema distribuito, Elixir/BEAM | Script Python single-file |
| **Integrazione PM** | Linear board, webhook, event-driven | Parametro `--task` da CLI |
| **Parallelismo** | Decine di agenti concorrenti | Un task per volta |
| **Proof of Work** | CI, PR review, video walkthrough | Exit code dell'agente + test del progetto |
| **Gestione fallimenti** | Supervision tree BEAM | Try/finally con ripristino directory |
| **Target** | Team engineering enterprise | Developer individuale o piccolo team |
| **Agenti supportati** | Codex (OpenAI) | Gemini CLI, OpenCode |

Symphony-Lite è il punto di partenza ideale per adottare la filosofia di **"gestire lavoro, non sessioni"** senza infrastruttura complessa.

---

## Come funziona

Il flusso di esecuzione si articola in tre fasi distinte:

### Fase 1 — Setup del Workspace Isolato

```
git clone <repo_url> ./symphony_workspace
git checkout -b symphony/<task-id>
```

Il workspace è sempre fresco: se ne esiste uno precedente, viene rimosso e ricreato. Il branch è nominato `symphony/<id>` per garantire isolamento e tracciabilità.

### Fase 2 — Esecuzione dell'Agente

L'agente CLI riceve un prompt strutturato che include:
- La **descrizione del task** fornita dall'utente.
- L'istruzione di seguire le specifiche operative in `GEMINI.md` o `WORKFLOW.md`.
- Il vincolo esplicito: **il task non è completo finché tutti i test non passano**.

```bash
# Con Gemini CLI (default)
gemini -y "<prompt>"

# Con OpenCode
opencode run "<prompt>"
```

### Fase 3 — Handoff

Se l'agente termina con successo:
- Viene rilevato se ci sono modifiche (`git status --porcelain`).
- Le modifiche vengono committate con messaggio standardizzato: `ai: modifiche autonome via Symphony-Light`.
- Il branch è pronto per il push e l'apertura di una Pull Request.

> **Nota:** il `git push` è commentato per sicurezza. Configurare SSH/token prima di abilitarlo.

---

## Requisiti

- **Python** 3.9 o superiore
- **Git** installato e nel PATH
- Almeno uno dei seguenti agenti CLI:
  - [`gemini` CLI](https://github.com/google-gemini/gemini-cli) (default)
  - [`opencode`](https://github.com/sst/opencode) (opzionale, via flag `--opencode`)
- Accesso in lettura al repository Git target

### Per il repository target

Il progetto su cui l'agente lavora dovrebbe seguire i principi dell'**Harness Engineering**:
- Un file `GEMINI.md` o `WORKFLOW.md` nella root che documenti:
  - Come installare le dipendenze
  - Come eseguire linter e formatter
  - Come eseguire la test suite
- Una test suite automatizzata che l'agente possa invocare per auto-validarsi

---

## Installazione

Symphony-Lite può essere installato localmente per essere richiamato ovunque:

```bash
# Clona questo repository
git clone https://github.com/<tuo-utente>/symphony_lite.git
cd symphony_lite

# (Opzionale ma consigliato) Crea un ambiente virtuale
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Installa il pacchetto in modalità editabile (include la CLI 'symphony-lite')
pip install -e .
```

---

## Utilizzo

### Esempio base (con Gemini CLI)

```bash
symphony-lite \
  --url https://github.com/tuo-org/tuo-repo.git \
  --task "Aggiungi la validazione dell'email nel form di registrazione" \
  --id feat-email-validation
```

### Esempio con OpenCode

```bash
symphony-lite \
  --url https://github.com/tuo-org/tuo-repo.git \
  --task "Correggi il bug #42: NullPointerException nel parser CSV" \
  --id fix-42 \
  --opencode
```

### Output atteso

```
Clonazione del repository https://github.com/tuo-org/tuo-repo.git...
Creazione del branch isolato: symphony/feat-email-validation...

[Symphony] Passaggio del controllo all'agente autonomo...
--------------------------------------------------
... (output dell'agente) ...
--------------------------------------------------
[Symphony] L'agente ha completato il ciclo di lavoro con successo!
Preparazione dell'Handoff (Push su GitHub)...

[DONE] Task completato! Controlla il branch 'symphony/feat-email-validation' o apri una Pull Request.
```

---

## Riferimento ai parametri CLI

| Flag | Alias | Obbligatorio | Default | Descrizione |
|---|---|---|---|---|
| `--url` | `-u` | ✅ | — | URL del repository Git da clonare |
| `--task` | `-t` | ✅ | — | Descrizione testuale del task da eseguire |
| `--id` | `-i` | ❌ | `task-auto` | ID univoco del task, usato per il nome del branch |
| `--opencode` | — | ❌ | `False` | Usa OpenCode invece di Gemini CLI come agente |

```bash
# Help completo
symphony-lite --help
```

---

## Il ruolo del file GEMINI.md / WORKFLOW.md

Questo file è il **"harness"** del progetto target: il documento che l'agente legge per capire come operare autonomamente nel codebase. È l'equivalente locale del concetto di *harness engineering* di OpenAI.

Un buon `GEMINI.md` dovrebbe contenere:

```markdown
## Setup
pip install -r requirements.txt

## Linting
ruff check . --fix
black .

## Test
pytest tests/ -v

## Note operative
- Non modificare i file in /docs
- Ogni nuova feature deve avere almeno un test unitario
- Il codice deve superare il linting prima del commit
```

Senza questo file, l'agente opererà senza vincoli di qualità definiti.

---

## Architettura del flusso

```
┌─────────────────────────────────────────────────────────────┐
│                        symphony_lite.py                      │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │    setup_    │    │  run_agent() │    │   handle_    │  │
│  │  isolated_   │───▶│              │───▶│  handoff()   │  │
│  │  workspace() │    │  gemini -y   │    │              │  │
│  │              │    │  opencode -y │    │  git add .   │  │
│  │  git clone   │    │              │    │  git commit  │  │
│  │  git checkout│    │  prompt con  │    │  (git push)  │  │
│  │  -b symphony/│    │  GEMINI.md   │    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                   │                   │           │
│         ▼                   ▼                   ▼           │
│    workspace/           agente AI          branch pronto    │
│    branch isolato       auto-valida        per PR review    │
└─────────────────────────────────────────────────────────────┘
```

### Gestione degli errori e dei processi

| Scenario | Comportamento |
|---|---|
| **Gestione Processi** | L'orchestratore gira nel proprio **process group** (`os.setpgrp`). |
| **Completamento Task** | Termina aggressivamente tutti i processi nel gruppo (`stop_all`) ed esce. |
| **Interruzione Utente** | `SIGINT` (Ctrl+C) o `SIGTERM` attivano `stop_all` per una pulizia completa. |
| Clone fallito | Git restituisce un errore, l'esecuzione si interrompe. |
| Agente fallito | L'handoff viene saltato e l'orchestratore esce con codice 1. |
| Nessuna modifica | L'handoff lo rileva e informa senza committare. |
| Ripristino directory | Il blocco `finally` assicura sempre il ripristino della directory originale. |

---

## Cosa Manca (Fuori Scope)

Rispetto alla SPEC ufficiale di Symphony, mancano volutamente i seguenti componenti, giudicati troppo complessi o non necessari per un uso locale e individuale:
1. **Integrazione Issue Tracker (SPEC §3.1)**: Collegamento diretto a Linear (o altri) per scaricare i task in "To Do" e aggiornare lo stato sulla board.
2. **Polling Daemon Loop (SPEC §8.1)**: Esecuzione come demone in background che interroga il tracker ogni X secondi.
3. **Concorrenza Multi-Agente (SPEC §8.3)**: Esecuzione e gestione di `max_concurrent_agents` in parallelo.
4. **Protocollo `codex app-server` (SPEC §5.3.6)**: Comunicazione strutturata in JSON via stdio con l'agente lanciato come server, invece di una semplice esecuzione CLI.
5. **Dynamic Reload (SPEC §6.2)**: Ricaricamento a caldo delle modifiche a `WORKFLOW.md` mentre il demone è in esecuzione.

---

## Roadmap

- [ ] **Supporto multi-task**: eseguire una lista di task in sequenza da file JSON/YAML
- [ ] **Integrazione Linear**: polling automatico del board per acquisire nuovi issue
- [ ] **Proof of Work strutturato**: parsing dell'output dei test e report in markdown
- [ ] **Notifiche**: webhook Slack/Discord al completamento del task
- [ ] **Retry automatico**: ritentativi configurabili se l'agente fallisce
- [ ] **Supporto Docker**: workspace completamente isolato via container
- [ ] **Dashboard web**: interfaccia per monitorare task in corso e completati

---

## Licenza

Questo progetto è distribuito con licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.

---

## Link utili

| Risorsa | Link |
|---|---|
| 🎼 Symphony (OpenAI) — GitHub | [github.com/openai/symphony](https://github.com/openai/symphony) |
| 📄 Symphony SPEC.md | [github.com/openai/symphony/blob/main/SPEC.md](https://github.com/openai/symphony/blob/main/SPEC.md) |
| 📖 OpenAI Blog — Annuncio Symphony | [openai.com/index/open-source-codex-orchestration-symphony/](https://openai.com/index/open-source-codex-orchestration-symphony/) |
| 🔧 Harness Engineering (OpenAI) | [openai.com/index/harness-engineering/](https://openai.com/index/harness-engineering/) |
| 🤖 Gemini CLI | [github.com/google-gemini/gemini-cli](https://github.com/google-gemini/gemini-cli) |
| ⚡ OpenCode | [github.com/sst/opencode](https://github.com/sst/opencode) |

---

<p align="center">
  <em>Costruito con la filosofia di Symphony: gestisci il lavoro, non le sessioni.</em>
</p>
