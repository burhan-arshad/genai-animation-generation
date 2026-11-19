# Film engine v2: sirf ye 2 cheezein replace karein (v1 ke baad)

| kya | kahan |
|---|---|
| `engine/styles/film/` (poora folder) | `engine\styles\film\` ko isi se replace karein. **Pehle** purane `example\tools` aur `example\fonts` folders kahin copy kar lein, ya replace ke baad dobara `python install_film_engine.py` chalayein (wo wapas daal deta hai) |
| `shorts_agent/filmboard.py` | `shorts_agent\filmboard.py` replace |

Baqi kuch nahi badla. Phir: `python install_film_engine.py`, uske baad purani job dobara: `python -m shorts_agent.preview --job N`.

## v2 mein kya behtar hua
- **Characters zinda lagte hain:** saans, sar ka halka hilna, bolte waqt sar ki harkat, chalte waqt haathon ki swing aur body bob, haath ke pose badalte waqt overshoot (jhatka).
- **Emotes:** mood badalne par sar ke upar "!" "?" pasina, ghussa, sitara, "HA" waghera pop hota hai.
- **Camera:** har shot mein halki sans, har cut par camera "settle" hota hai.
- **Roshni aur depth:** suraj ki kirnen, parindey, foreground ghaas (parallax), khidki se roshni ki shuayein, pedon ka hilna, har cheez ke neeche saya.
- **Text animation:** numbers 0 se count-up hote hain (25 CENTS), labels typewriter ki tarah likhte hain; saal (1869) count nahi hote.
- **Hero ka intro:** hero ab andar chalta hua aata hai, haath hilata hai, phir tasveer dikhata hai; end par sar hilata hai aur muskurata hai.
- **Director prompt:** Gemini ko ab "layers mein banao" (peechay scenery, beech mein action, aage chhoti cheezein), cheez haath mein pakdao, reveal ko event banao.
