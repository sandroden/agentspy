# Obiettivo
Questo progetto vuole creare un softwre dal compito prevalentemente
didattico per spiare la comunucazine fra claude code e LLM mostrando
come questa è composta:
 * system prompt
 * tools
 * user context
 * user prompt
 * tool request
 * agents
 
 l'idea è di sfruttare il payload degli hooks per spiare il contenuto
 che viene trasmesso.
 
 
 uno dei punti fondamentali sarà i avere uno strumento didattico ed
 agile per capire il vantaggio di una strategia rispetto ad un'altra
 
 un progetto analogo da cui possiamo ispirarci è qui:
 /home/sandro/src/git/claude-code-hooks-multi-agent-observability
 
 dove i realtà il problema maggiore è il fatto che non mi piace la
 renderizzazione dei dati. Si può anche valutare di sfruttare la parte
 di raccolta dati per renderizzarla in altro modo.
 
 Fra le cose che io voglio potere fare è seguire il flusso di un
 subagente o seguire tutti i round trip che seguono uno user prompt
 per capire come viene impiegato il contesto, mostrare ad esempio
 visivamente il rimpimento del contesto, il totale e dove viene usato.
 
## Conoscenza (.okf/)

Bundle di conoscenza OKF in `.okf/` — indice in `.okf/index.md`.

- **Prima** di esplorare a colpi di grep o lettura diretta del codice, consulta
  `.okf/index.md` e i concept pertinenti (skill OKF, modalità "consume"). Per
  modifiche vere e proprie, verifica comunque sul codice: i concept possono
  essere disallineati.
- **Dopo** modifiche significative, valuta se aggiornare il bundle (skill OKF,
  modalità "maintain"), insieme alla proposta di commit.
  
