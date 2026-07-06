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
 
