<img width="223" height="150" alt="archi_mvp" src="https://github.com/user-attachments/assets/34ca3a68-fb4f-40f4-b7a5-e9293d4a1507" />Système de recommandation d'articles — My Content

MVP d'un système de recommandation d'articles de presse, déployé en architecture serverless sur Azure Functions.

Le besoin fonctionnel tient en une phrase : en tant qu'utilisateur de l'application, je reçois une sélection de cinq articles. L'ensemble du projet est construit autour de cette user story, avec une contrainte structurante — l'architecture doit absorber l'arrivée de nouveaux utilisateurs et de nouveaux articles.

Données

Jeu de données Globo.com — news portal user interactions, non versionné dans ce dépôt.

	
Articles au catalogue	364 047
Interactions	2 988 181
Utilisateurs	322 897
Embeddings fournis	364 047 × 250 (float32, 364 Mo)
Constats qui orientent les choix techniques

Période exploitable : 1er au 16 octobre 2017. Le volume d'interactions chute de plus de 99 % à partir du 17 octobre — de 190 000 clics quotidiens à quelques dizaines. Les interactions résiduelles proviennent à 96 % d'utilisateurs déjà observés, ce qui traduit un changement de périmètre de collecte plutôt qu'une évolution du comportement. La période retenue exclut cette portion.

Historique très court. Médiane de 4 clics par utilisateur, premier quartile à 2. La distribution est fortement asymétrique (moyenne 9,25, maximum 1232) : une minorité d'utilisateurs très actifs coexiste avec une masse de visiteurs occasionnels. Le filtrage collaboratif dispose donc de peu de signal pour la majorité de la population.

Catalogue largement inexploré. 46 033 articles ont été cliqués au moins une fois, soit 12,6 % du catalogue. Près de 9 articles sur 10 sont invisibles pour un modèle collaboratif, quel que soit son entraînement. Seule une approche par le contenu peut les faire remonter.

Cold start mesuré. Sur un découpage temporel au 14 octobre, 20,6 % des utilisateurs actifs en test (19 771 sur 95 773) n'apparaissent pas dans la période d'entraînement. Le cas du nouvel utilisateur n'est pas théorique : il concerne un utilisateur sur cinq.

Modèles
Content-based filtering

Le profil d'un utilisateur est la moyenne des embeddings des articles qu'il a consultés. La recommandation retient les cinq articles du catalogue dont la similarité cosinus avec ce profil est la plus forte, en excluant ceux déjà lus.

Deux stratégies de construction du profil ont été comparées :

moyenne des embeddings — retenue ; agrège plusieurs centres d'intérêt et produit des recommandations plus diversifiées ;
dernier article consulté — capte mieux l'intention immédiate, mais ramène le voisinage direct d'un seul article et enferme thématiquement.

Le recouvrement de catégories entre articles lus et articles recommandés s'établit à 72,9 % : continuité thématique forte, sans fermeture complète à la découverte. Cette approche ne nécessite aucun entraînement et fonctionne dès le premier clic.

Collaborative filtering

Factorisation matricielle par ALS (bibliothèque implicit), sur un échantillon de 5 000 utilisateurs ayant au moins 5 clics — soit une matrice 5 000 × 6 673 à 73 992 interactions (densité 0,22 %), décomposée en 50 facteurs latents.

Le jeu de données ne comporte aucune note explicite. Le rating implicite est le nombre de clics d'un utilisateur sur un article, mais 98,8 % des paires sont à un seul clic : le signal est en pratique binaire. C'est pourquoi un algorithme de feedback implicite est employé plutôt qu'une factorisation conçue pour des notes explicites.

La colonne session_size n'est pas utilisée comme rating : elle compte les clics de l'ensemble d'une session et n'est pas rattachable à un article particulier.

Réduction de dimension

Le fichier d'embeddings d'origine pèse 364 Mo, incompatible avec les limites du plan Consumption. Une ACP le ramène de 250 à 50 dimensions :

Composantes	Variance expliquée
20	70,7 %
30	83,0 %
50	94,5 %
100	98,7 %

À 50 composantes, le fichier passe à 72,8 Mo pour 94,5 % de variance conservée. Les recommandations produites partagent en moyenne 3 articles sur 5 avec celles calculées sur les embeddings complets.

Architecture MVP

Afficher l'image

Description fonctionnelle

Les artefacts sont produits hors ligne dans le notebook, puis déposés dans un conteneur Blob. L'Azure Function les charge au premier appel de chaque instance et les conserve en mémoire ; les appels suivants ne déclenchent aucun téléchargement.

À réception d'un user_id, la Function applique une cascade à trois branches :

Condition	Méthode	Justification
user_id présent dans le modèle ALS	Filtrage collaboratif	Facteurs latents disponibles
Absent d'ALS, historique connu	Content-based	Aucun entraînement requis, opérationnel dès 1 clic
Aucun historique	Popularité	Seule information disponible

La réponse JSON expose la méthode employée, ce qui rend le comportement observable depuis l'interface :

json
{"user_id": 99653, "articles": [313431, 156964, 70646, 156619, 119193], "methode": "collaboratif"}
Composants déployés
Azure Function (plan Consumption, Python 3.10) — trigger HTTP anonyme sur /api/recommend
Blob Storage, conteneur models — embeddings réduits, facteurs ALS, mappings d'identifiants, historiques de 50 000 utilisateurs, top popularité
Application Streamlit locale — liste déroulante d'identifiants, saisie libre pour tester un identifiant arbitraire, bascule entre l'API locale et l'API déployée
Architecture cible

Afficher l'image

L'architecture MVP calcule tout à la demande et s'appuie sur des fichiers figés. En production, deux évolutions s'imposent.

Précalcul et service depuis Cosmos DB. Un traitement distribué périodique réentraîne le modèle sur la population complète et stocke les cinq articles de chaque utilisateur, indexés par user_id. La Function se réduit alors à une lecture indexée : la latence devient indépendante de la taille du catalogue.

Encodage des articles à la publication. Chaque nouvel article est vectorisé dès sa mise en ligne et son embedding rejoint le Blob, sans attendre le cycle de réentraînement.

Réponse aux deux contraintes

Nouvel utilisateur. Il n'a pas de ligne en base entre deux batchs. La branche content-based le prend en charge dès son premier clic, à partir des embeddings et de son historique de session. Il entre dans le précalcul au cycle suivant.

Nouvel article. Il est recommandable immédiatement par similarité de contenu, puisque son embedding existe. Le collaboratif, lui, ne pourra le proposer qu'après avoir observé suffisamment de clics — ce qui, rapporté aux 87 % du catalogue jamais cliqué, ne se produira jamais pour la majorité des articles.

C'est ce qui rend la cascade structurelle plutôt que palliative : elle ne compense pas une défaillance, elle absorbe le décalage inhérent entre un modèle entraîné par lots et un flux éditorial continu.

Structure du dépôt
![Up<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 660" font-family="Segoe UI, Helvetica, Arial, sans-serif">
  <rect width="980" height="660" fill="#ffffff"/>

  <text x="490" y="38" text-anchor="middle" font-size="22" font-weight="600" fill="#1a1a2e">Architecture MVP — My Content</text>
  <text x="490" y="60" text-anchor="middle" font-size="13" fill="#666">Système de recommandation d'articles — état actuel</text>

  <!-- ===================== HORS LIGNE ===================== -->
  <rect x="30" y="90" width="270" height="250" rx="8" fill="#f4f6fb" stroke="#c3cbe0" stroke-width="1.5" stroke-dasharray="6 4"/>
  <text x="45" y="112" font-size="12" font-weight="600" fill="#5a6784">TRAITEMENT HORS LIGNE (notebook)</text>

  <rect x="50" y="126" width="230" height="44" rx="6" fill="#ffffff" stroke="#8b9dc3" stroke-width="1.5"/>
  <text x="165" y="144" text-anchor="middle" font-size="12.5" font-weight="600" fill="#2c3e57">Dataset Globo.com</text>
  <text x="165" y="160" text-anchor="middle" font-size="11" fill="#6b7a99">2,99 M clics · 364 047 articles</text>

  <path d="M165 170 L165 192" stroke="#8b9dc3" stroke-width="1.5" marker-end="url(#ar)"/>

  <rect x="50" y="192" width="230" height="60" rx="6" fill="#ffffff" stroke="#8b9dc3" stroke-width="1.5"/>
  <text x="165" y="210" text-anchor="middle" font-size="12.5" font-weight="600" fill="#2c3e57">Entraînement</text>
  <text x="165" y="226" text-anchor="middle" font-size="11" fill="#6b7a99">ALS (50 facteurs, 5 000 users)</text>
  <text x="165" y="241" text-anchor="middle" font-size="11" fill="#6b7a99">PCA 250 → 50 dim (94,5 % var.)</text>

  <path d="M165 252 L165 274" stroke="#8b9dc3" stroke-width="1.5" marker-end="url(#ar)"/>

  <rect x="50" y="274" width="230" height="48" rx="6" fill="#ffffff" stroke="#8b9dc3" stroke-width="1.5"/>
  <text x="165" y="292" text-anchor="middle" font-size="12.5" font-weight="600" fill="#2c3e57">Export des artefacts</text>
  <text x="165" y="308" text-anchor="middle" font-size="11" fill="#6b7a99">.npy · .pkl</text>

  <!-- flèche vers blob -->
  <path d="M280 298 L400 298 L400 268" stroke="#8b9dc3" stroke-width="1.5" fill="none" marker-end="url(#ar)"/>
  <text x="340" y="292" text-anchor="middle" font-size="10.5" fill="#6b7a99">upload</text>

  <!-- ===================== AZURE ===================== -->
  <rect x="330" y="90" width="620" height="290" rx="8" fill="#eef4fc" stroke="#7aa5d2" stroke-width="1.5"/>
  <text x="345" y="112" font-size="12" font-weight="600" fill="#2b5f92">MICROSOFT AZURE — plan Consumption (serverless)</text>

  <!-- blob -->
  <rect x="350" y="126" width="180" height="142" rx="6" fill="#ffffff" stroke="#4a86c8" stroke-width="1.5"/>
  <text x="440" y="146" text-anchor="middle" font-size="12.5" font-weight="600" fill="#1f4e79">Blob Storage</text>
  <text x="440" y="160" text-anchor="middle" font-size="10.5" fill="#6b7a99">conteneur « models »</text>
  <line x1="364" y1="170" x2="516" y2="170" stroke="#dde5f0"/>
  <text x="366" y="186" font-size="10.5" fill="#44546a">emb_pca50.npy — 73 Mo</text>
  <text x="366" y="202" font-size="10.5" fill="#44546a">als_user_factors.npy</text>
  <text x="366" y="218" font-size="10.5" fill="#44546a">als_item_factors.npy</text>
  <text x="366" y="234" font-size="10.5" fill="#44546a">als_mappings.pkl</text>
  <text x="366" y="250" font-size="10.5" fill="#44546a">hist_users.pkl — 50 000</text>
  <text x="366" y="263" font-size="10.5" fill="#44546a">top_popular.pkl</text>

  <path d="M530 196 L580 196" stroke="#4a86c8" stroke-width="1.5" marker-end="url(#arb)"/>
  <text x="555" y="189" text-anchor="middle" font-size="10" fill="#4a86c8">lecture</text>
  <text x="555" y="211" text-anchor="middle" font-size="9.5" fill="#8fa3bd">1× / instance</text>

  <!-- function -->
  <rect x="580" y="126" width="350" height="230" rx="6" fill="#ffffff" stroke="#4a86c8" stroke-width="2"/>
  <text x="755" y="147" text-anchor="middle" font-size="13" font-weight="600" fill="#1f4e79">Azure Function — /api/recommend</text>
  <text x="755" y="162" text-anchor="middle" font-size="10.5" fill="#6b7a99">HTTP trigger · Python 3.10 · cache mémoire</text>

  <text x="600" y="186" font-size="11" font-weight="600" fill="#44546a">Cascade de sélection</text>

  <rect x="600" y="194" width="310" height="40" rx="5" fill="#e8f5e9" stroke="#66a86e" stroke-width="1.2"/>
  <text x="612" y="211" font-size="11.5" font-weight="600" fill="#2e6b36">1 · user_id ∈ modèle ALS</text>
  <text x="612" y="226" font-size="10.5" fill="#4a7c52">→ filtrage collaboratif</text>

  <rect x="600" y="240" width="310" height="40" rx="5" fill="#fff6e5" stroke="#d9a441" stroke-width="1.2"/>
  <text x="612" y="257" font-size="11.5" font-weight="600" fill="#8a6316">2 · sinon, historique connu</text>
  <text x="612" y="272" font-size="10.5" fill="#a07b2c">→ content-based (cosinus sur embeddings)</text>

  <rect x="600" y="286" width="310" height="40" rx="5" fill="#fdecec" stroke="#cc7a7a" stroke-width="1.2"/>
  <text x="612" y="303" font-size="11.5" font-weight="600" fill="#8f3b3b">3 · sinon, utilisateur inconnu</text>
  <text x="612" y="318" font-size="10.5" fill="#a85555">→ popularité (cold start)</text>

  <text x="755" y="345" text-anchor="middle" font-size="10.5" fill="#6b7a99">Réponse JSON : user_id · articles[5] · methode</text>

  <!-- ===================== CLIENT ===================== -->
  <rect x="330" y="415" width="620" height="120" rx="8" fill="#f7f4fb" stroke="#a98fc4" stroke-width="1.5"/>
  <text x="345" y="437" font-size="12" font-weight="600" fill="#6a4a8f">POSTE UTILISATEUR</text>

  <rect x="350" y="450" width="260" height="66" rx="6" fill="#ffffff" stroke="#9b7cc0" stroke-width="1.5"/>
  <text x="480" y="470" text-anchor="middle" font-size="12.5" font-weight="600" fill="#553875">Application Streamlit</text>
  <text x="480" y="487" text-anchor="middle" font-size="10.5" fill="#6b7a99">liste de 200 id · saisie libre</text>
  <text x="480" y="502" text-anchor="middle" font-size="10.5" fill="#6b7a99">bascule Azure / local</text>

  <rect x="660" y="450" width="260" height="66" rx="6" fill="#ffffff" stroke="#9b7cc0" stroke-width="1.5" stroke-dasharray="5 3"/>
  <text x="790" y="470" text-anchor="middle" font-size="12.5" font-weight="600" fill="#553875">Function locale (func start)</text>
  <text x="790" y="487" text-anchor="middle" font-size="10.5" fill="#6b7a99">localhost:7071</text>
  <text x="790" y="502" text-anchor="middle" font-size="10.5" fill="#6b7a99">mise au point et tests</text>

  <!-- flèches client -> function -->
  <path d="M480 450 L480 380" stroke="#9b7cc0" stroke-width="1.8" fill="none" marker-end="url(#arp)"/>
  <text x="472" y="404" text-anchor="end" font-size="10.5" fill="#7a5c9e">GET ?user_id=…</text>

  <path d="M610 483 L660 483" stroke="#9b7cc0" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#arp)"/>

  <path d="M930 296 L950 296 L950 400 L500 400 L500 450" stroke="#7aa5d2" stroke-width="1.5" fill="none" marker-end="url(#arp)" opacity="0"/>

  <!-- legende -->
  <rect x="30" y="565" width="920" height="66" rx="6" fill="#fafbfd" stroke="#dde2ec"/>
  <text x="45" y="586" font-size="11.5" font-weight="600" fill="#44546a">Flux nominal</text>
  <text x="45" y="604" font-size="11" fill="#6b7a99">L'utilisateur choisit un identifiant dans l'interface → appel HTTP à l'Azure Function → chargement des artefacts depuis le Blob (premier appel</text>
  <text x="45" y="620" font-size="11" fill="#6b7a99">de l'instance uniquement, puis cache mémoire) → sélection de la branche selon l'identifiant → renvoi des 5 articles et de la méthode employée.</text>

  <defs>
    <marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#8b9dc3"/>
    </marker>
    <marker id="arb" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#4a86c8"/>
    </marker>
    <marker id="arp" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L8,3 z" fill="#9b7cc0"/>
    </marker>
  </defs>
</svg>
loading archi_mvp.svg…]()


Les données brutes, les artefacts de modèles et local.settings.json (qui contient la chaîne de connexion) sont exclus du versionnement.

Installation
bash
python3.10 -m venv .venv310
source .venv310/bin/activate
pip install -r requirements.txt

Télécharger le jeu de données et le placer dans news-portal-user-interactions-by-globocom/, puis exécuter le notebook pour régénérer les artefacts.

Function en local
bash
cd azure_function
func start

Renseigner au préalable STORAGE_CONNECTION dans local.settings.json.

Application
bash
streamlit run app/app.py

L'interface permet de basculer entre l'API locale (localhost:7071) et l'API déployée.

Choix de conception

Échantillon de 5 000 utilisateurs pour ALS. Calculer les similarités pour l'ensemble des 322 897 utilisateurs est hors de portée dans un cadre MVP. Le filtre à 5 clics minimum garantit un historique exploitable. L'échantillon est volontairement favorable au collaboratif, ce qui invite à interpréter avec prudence toute comparaison avec le content-based.

50 000 historiques embarqués. Au-delà des 5 000 utilisateurs du modèle, les historiques des utilisateurs les plus actifs (limités à 20 articles chacun, 4,8 Mo au total) permettent à la branche content-based de traiter des identifiants absents du modèle collaboratif. Sans eux, la cascade se réduirait à deux branches.

Cache mémoire dans la Function. Les artefacts sont chargés une fois par instance. Le premier appel après une période d'inactivité subit le démarrage à froid du plan Consumption, cumulé au téléchargement des 73 Mo ; les suivants répondent immédiatement tant que l'instance reste active.
