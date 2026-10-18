"""Campagnes V6 : 3 factions, chacune avec un tutoriel guidé et 6 missions. Progression en JSON."""
import copy
import json
import os

from game import ABILITY, FACTIONS

NMISSIONS = 7   # 0 = tutoriel, 1..6 = missions


def T(fac):
    f = FACTIONS[fac]
    d = dict(f['units'])
    d.update({k: v for k, v in f['blds'].items()})
    d['ability'] = ABILITY[fac]['name']
    d['ability_desc'] = ABILITY[fac]['desc']
    return d


def tutorial_steps(fac):
    n = T(fac)
    S = [
        ("Bienvenue, commandant", "Glissez un doigt pour déplacer la caméra. Pincez avec deux doigts pour zoomer, ou touchez la minicarte en haut à droite.", ('any', ['pan', 'zoom', 'minimap'])),
        ("Sélectionner une unité", "Touchez un %s pour le sélectionner (un anneau vert apparaît sous ses pieds)." % n['worker'].lower(), ('flag', 'select_worker')),
        ("Récolter du bois", "Le %s étant sélectionné, touchez un arbre : il ira couper du bois et le rapportera à votre %s." % (n['worker'].lower(), n['hq'].lower()), ('flag', 'harvest')),
        ("Faire tourner l'économie", "Envoyez aussi les autres ouvriers récolter (arbres = bois, cristaux = minerai). Objectif : 150 ressources récoltées.", ('gathered', 150)),
        ("Produire des unités", "Touchez votre %s, puis la carte « %s » dans la barre du bas pour en entraîner un de plus." % (n['hq'].lower(), n['worker']), ('flag', 'prod_worker')),
        ("Construire", "Sélectionnez un %s, touchez « %s », glissez l'aperçu près de votre base (vert = valide) puis appuyez sur « Poser ici »." % (n['worker'].lower(), n['barracks']), ('flag', 'place_barracks')),
        ("Patience", "Vos ouvriers construisent : plus ils sont nombreux, plus c'est rapide. Attendez la fin du chantier (%s)." % n['barracks'], ('bld', 'barracks', 1)),
        ("Entraîner une armée", "Sélectionnez la %s et entraînez 3 %ss. Les unités de combat se règlent sur l'ennemi : le %s bat le cavalier, le cavalier bat l'archer, l'archer bat le soldat." % (n['barracks'].lower(), n['soldier'].lower(), n['soldier'].lower()), ('unit', 'soldier', 3)),
        ("Rassembler les troupes", "Touchez le bouton « Armée » à gauche : toutes vos unités de combat sont sélectionnées.", ('flag', 'btn_army')),
        ("Déplacer les troupes", "Touchez le sol : vos soldats s'y rendent. (Le bouton « Attaquer » les fait combattre en chemin.)", ('flag', 'move')),
        ("La forge", "Construisez une %s avec un ouvrier. Elle sert à améliorer vos armes et armures." % n['forge'], ('bld', 'forge', 1)),
        ("Recherche technologique", "Sélectionnez la %s et lancez une recherche : l'amélioration s'applique à toutes vos unités." % n['forge'], ('flag', 'research')),
        ("Pouvoir de faction", "Sélectionnez votre %s : le bouton « %s » libère le pouvoir de votre peuple. %s" % (n['hq'].lower(), n['ability'], n['ability_desc']), ('flag', 'ability')),
        ("Au combat !", "Un avant-poste ennemi s'est installé au centre de la carte. Envoyez vos troupes (bouton « Attaquer ») et détruisez sa %s." % n['barracks'].lower(), ('destroy', 'barracks')),
    ]
    return [dict(title=a, text=b, c=c) for a, b, c in S]


def tut(fac, title, brief, win):
    return dict(title=title, enemy={'kingdom': 'horde', 'horde': 'kingdom', 'sylvan': 'horde'}[fac], diff=0, seed=900 + len(fac), tutorial=True,
                passive=True, brief=brief, win=win,
                setup=dict(res=(800, 600), extra=[(1, 'bld', 'barracks', 980, 960), (1, 'unit', 'soldier', 940, 1010), (1, 'unit', 'soldier', 1010, 1010)],
                           mission=dict(steps=tutorial_steps(fac))))


def M(title, enemy, diff, seed, brief, win, objs, setup=None, limit=None, ai=None):
    st = copy.deepcopy(setup or {})
    st['mission'] = dict(obj=objs, limit=limit)
    if ai:
        st['ai'] = ai
    return dict(title=title, enemy=enemy, diff=diff, seed=seed, brief=brief, win=win, setup=st)


CAMPAIGNS = {
    'kingdom': dict(
        title='La Couronne en Péril',
        intro="Le roi Aurèle est mort sans héritier. Des hordes venues du nord brûlent les villages de la frontière. "
              "Vous êtes le dernier maréchal du royaume : à vous de sauver la couronne.",
        missions=[
            tut('kingdom', "L'école du maréchal",
                "Avant de guider l'armée du royaume, apprenez le métier : récolte, construction, armée, technologies et pouvoir royal. "
                "L'ennemi est passif : prenez votre temps.",
                "Vous maîtrisez les bases. Le royaume a besoin de vous, maréchal !"),
            M('Les feux de la frontière', 'horde', 1, 102,
              "Une horde rôde à la frontière et vise votre château. Deux tours de guet vous protègent déjà. "
              "Tenez 7 minutes : des renforts royaux arriveront à l'aube.",
              "L'aube se lève et les orcs battent en retraite. La frontière est sauve !",
              [dict(t='survive', n=420)],
              dict(res=(300, 150), blds=[('tower', 190, -80), ('tower', 80, -200), ('barracks', 160, 70)], units=[('soldier', 3), ('archer', 2)]),
              ai=dict(grace=45, wave_n=4, think=0.9)),
            M('Le gué de la Rive-Haute', 'horde', 1, 103,
              "Les orcs traversent la rivière par vagues. Tenez le gué et abattez 25 d'entre eux : la nouvelle de leur défaite "
              "calmera les clans pour un temps.",
              "Le gué est rouge de sang orc. Les clans hésitent à revenir.",
              [dict(t='kills', n=25)],
              dict(res=(350, 200), blds=[('barracks', 160, 70), ('tower', 180, -90)], units=[('soldier', 4), ('archer', 3)]),
              ai=dict(grace=50, wave_n=3, think=0.8)),
            M('La forge du roi', 'horde', 1, 104,
              "Le roi défunt avait rêvé d'une armée moderne. Bâtissez une forge royale et une chapelle, perfectionnez vos armes "
              "(4 recherches) et réunissez 12 combattants. L'ennemi vous laisse un peu de répit.",
              "Les marteaux résonnent dans tout le château. L'armée d'Aurèle n'a jamais été si bien équipée.",
              [dict(t='bld', kind='forge', n=1), dict(t='bld', kind='temple', n=1), dict(t='techs', n=4), dict(t='army', n=12)],
              dict(res=(500, 300), blds=[('barracks', 160, 70), ('stable', 40, 190)], units=[('soldier', 2)]),
              ai=dict(grace=380)),
            M('La nuit des loups', 'horde', 2, 105,
              "Cette nuit, les chevaucheurs de loups attaquent par surprise. Vos tours et vos prêtres sont vos meilleurs atouts : "
              "tenez jusqu'au matin (8 minutes) et utilisez l'Ordre royal au bon moment.",
              "Au matin, les loups se sont enfuis dans la forêt. Le château tient toujours !",
              [dict(t='survive', n=480)],
              dict(res=(250, 150), blds=[('tower', 190, -80), ('tower', 80, -200), ('tower', 250, 40), ('barracks', 160, 70), ('temple', 50, 200)],
                   units=[('soldier', 4), ('archer', 4), ('healer', 2)],
                   e_units=[('knight', 4)]),
              ai=dict(grace=35, wave_n=5, think=0.7)),
            M("L'assaut des avant-postes", 'horde', 2, 106,
              "Il faut frapper la Horde au cœur : détruisez sa caserne et sa tanière avant 15 minutes. "
              "Vos catapultes sont redoutables contre les bâtiments.",
              "Les avant-postes brûlent. La Horde a perdu ses points d'appui.",
              [dict(t='destroy', kind='barracks'), dict(t='destroy', kind='stable')],
              dict(res=(600, 400), blds=[('barracks', 160, 70), ('forge', 30, 200)],
                   units=[('soldier', 5), ('archer', 4), ('knight', 2), ('heavy', 1)], e_blds=[('tower', -190, 90), ('tower', -80, 210)]),
              limit=900, ai=dict(grace=200)),
            M('La prise de Gorak-Dum', 'horde', 2, 107,
              "Le chef de guerre Gorak s'est retranché dans sa forteresse, hérissée de tours. Rassemblez soldats, archers, "
              "chevaliers, catapultes et prêtres, puis détruisez sa base. C'est la bataille décisive.",
              "Gorak-Dum est en flammes. La couronne est sauvée : vive le royaume !",
              [dict(t='hq')],
              dict(res=(700, 500), blds=[('barracks', 160, 70), ('forge', 30, 200), ('temple', 250, 40)],
                   units=[('soldier', 5), ('archer', 4), ('knight', 2), ('heavy', 2), ('healer', 2)], e_res=(500, 300),
                   e_units=[('soldier', 6), ('heavy', 2)], e_blds=[('tower', -190, 90), ('tower', -80, 210), ('tower', -230, -30)]),
              ai=dict(grace=240)),
        ]),
    'horde': dict(
        title='Le Chant de Guerre',
        intro="Gorak a uni les clans. Le chant de guerre résonne dans les collines : les terres fertiles des hommes "
              "seront à la Horde ! Montrez à Aurèle ce que valent les crocs de vos loups.",
        missions=[
            tut('horde', 'La première chasse',
                "Le jeune chef que vous êtes doit encore faire ses preuves. Apprenez à récolter, bâtir, forger et lancer la Fureur sanguinaire. "
                "Les ennemis sont passifs : chassez à votre rythme.",
                "Gorak sourit : vous êtes prêt pour la guerre !"),
            M('Razzia', 'kingdom', 0, 202,
              "Un village royal mal défendu se dresse près de vos terres. Vos chevaucheurs de loup sont rapides : "
              "frappez avant que les humains ne réagissent et détruisez leur château.",
              "Le village flambe ! Les clans acclament Gorak.",
              [dict(t='hq')],
              dict(res=(250, 100), units=[('knight', 3)]), ai=dict(grace=400)),
            M('Pillage des fermes', 'kingdom', 1, 203,
              "La Horde a faim. Récoltez 2000 ressources en 20 minutes pour nourrir les clans et forger des armes, "
              "pendant que les humains tentent de vous déloger.",
              "Les réserves débordent. Les forges de Gorak-Dum tournent à plein régime !",
              [dict(t='gather', n=2000)],
              dict(res=(200, 100), units=[('soldier', 2)]), limit=1200, ai=dict(grace=170, wave_n=4)),
            M('Le totem sanglant', 'kingdom', 1, 204,
              "Les anciens exigent une offrande : érigez la fosse des ogres, entraînez 3 ogres et obtenez 3 recherches. "
              "La Horde saura que l'heure est venue.",
              "Les ogres rugissent autour du totem. Rien n'arrêtera la Horde.",
              [dict(t='bld', kind='sanctum', n=1), dict(t='unit', kind='heavy', n=3), dict(t='techs', n=3)],
              dict(res=(500, 300), blds=[('barracks', 160, 70), ('forge', 30, 200)], units=[('soldier', 3)]), ai=dict(grace=380)),
            M('Les murs de pierre', 'kingdom', 2, 205,
              "Les humains ont bâti des tours de guet tout le long de la frontière. Rasez leurs tours et leur caserne "
              "avant 17 minutes : les ogres sont faits pour ça.",
              "Les murs de pierre ne sont plus que gravats. La route d'Aurèle est ouverte !",
              [dict(t='destroy', kind='tower'), dict(t='destroy', kind='barracks')],
              dict(res=(600, 400), blds=[('barracks', 160, 70), ('forge', 30, 200), ('sanctum', 250, 40)],
                   units=[('soldier', 4), ('heavy', 2), ('knight', 2)], e_blds=[('tower', -190, 90), ('tower', -80, 210), ('tower', -230, -30), ('tower', -330, 120)]),
              limit=1020, ai=dict(grace=220)),
            M("L'embuscade des elfes", 'sylvan', 2, 206,
              "Les elfes de la forêt vous ont tendu une embuscade ! Leurs archers ont une portée terrible : "
              "chargez-les avec vos loups et abattez 30 elfes. La Fureur sanguinaire fera la différence.",
              "Les elfes fuient sous les crocs des loups. La forêt tremble.",
              [dict(t='kills', n=30)],
              dict(res=(350, 250), blds=[('barracks', 160, 70), ('stable', 40, 190)], units=[('knight', 4), ('soldier', 4), ('healer', 1)]),
              ai=dict(grace=40, wave_n=4, think=0.8)),
            M("Le siège d'Aurèle", 'kingdom', 2, 207,
              "Le château du roi Aurèle est devant vous, défendu par des tours et une garde nombreuse. "
              "Faites donner les grunts, les ogres et les loups : cette nuit, la couronne change de maître.",
              "Le château tombe. La Horde règne désormais sur toutes les terres !",
              [dict(t='hq')],
              dict(res=(700, 500), blds=[('barracks', 160, 70), ('forge', 30, 200), ('temple', 250, 40)],
                   units=[('soldier', 5), ('knight', 3), ('heavy', 2), ('archer', 3), ('healer', 1)], e_res=(500, 300),
                   e_units=[('soldier', 5), ('archer', 3), ('heavy', 2)], e_blds=[('tower', -190, 90), ('tower', -80, 210), ('tower', -230, -30), ('tower', -330, 120)]),
              ai=dict(grace=220)),
        ]),
    'sylvan': dict(
        title="L'Éveil de la Forêt",
        intro="Depuis mille ans, la forêt d'Elenwë dort sous la protection des elfes. Mais la Horde abat les arbres "
              "sacrés. Les sentinelles s'éveillent : il est temps de défendre la forêt.",
        missions=[
            tut('sylvan', 'Les premiers pas sous les arbres',
                "Les anciens de l'Arbre-cité vous enseignent l'art de la forêt : récolte, bâtiments, bosquet ancestral et Souffle de la forêt. "
                "Aucun danger : la forêt veille.",
                "Les arbres murmurent votre nom. Vous êtes prêt à défendre Elenwë !"),
            M('Les sentinelles', 'horde', 0, 302,
              "Des éclaireurs orcs approchent de l'Arbre-cité. Une tour-fleur et quelques gardes veillent. "
              "Tenez 6 minutes, le temps que les rôdeurs reviennent de patrouille.",
              "Les orcs reculent devant l'éclat des tours-fleurs. La forêt est sauve, pour l'instant.",
              [dict(t='survive', n=360)],
              dict(res=(250, 120), blds=[('tower', 190, -80), ('barracks', 160, 70)], units=[('archer', 3), ('soldier', 1)]),
              ai=dict(grace=60, wave_n=4, think=1.2)),
            M('Les archers de la lune', 'horde', 1, 303,
              "Les rôdeurs sont la fierté d'Elenwë : leurs flèches portent plus loin que celles de n'importe quel peuple. "
              "Entraînez 10 rôdeurs et 2 druides pour la grande offensive.",
              "Dix archers de la lune bandent leur arc, soutenus par les druides. Les orcs ne passeront plus.",
              [dict(t='army', n=10, kind='archer'), dict(t='unit', kind='healer', n=2)],
              dict(res=(350, 250), blds=[('barracks', 160, 70), ('forge', 30, 200), ('temple', 250, 40)], units=[('archer', 2)]),
              ai=dict(grace=360)),
            M('Le sanctuaire des Ents', 'horde', 1, 304,
              "Au cœur du bois, les Ents sommeillent. Bâtissez leur sanctuaire, éveillez 3 Ents et obtenez 3 recherches : "
              "la forêt entière marchera à vos côtés.",
              "Trois Ents se dressent, vieux comme les montagnes. La Horde doit trembler.",
              [dict(t='bld', kind='sanctum', n=1), dict(t='unit', kind='heavy', n=3), dict(t='techs', n=3)],
              dict(res=(500, 300), blds=[('barracks', 160, 70), ('forge', 30, 200)], units=[('archer', 3), ('soldier', 1)]),
              ai=dict(grace=380)),
            M("La brume d'Elenwë", 'horde', 2, 305,
              "Une brume maléfique recouvre la forêt et la Horde en profite. Vos ressources sont maigres : "
              "économisez, soignez vos troupes avec les druides, et tenez 9 minutes.",
              "La brume se dissipe sous le chant des druides. Elenwë respire à nouveau.",
              [dict(t='survive', n=540)],
              dict(res=(200, 100), blds=[('tower', 190, -80), ('tower', 80, -200), ('tower', 250, 40), ('barracks', 160, 70), ('temple', 50, 200)],
                   units=[('archer', 5), ('soldier', 3), ('healer', 2)], e_units=[('soldier', 3)]),
              ai=dict(grace=30, wave_n=5, think=0.7)),
            M('La reconquête', 'horde', 2, 306,
              "Reprenez le terrain perdu : détruisez les tours de la Horde et sa caserne avant 17 minutes. "
              "Vos Ents tiennent les tours à distance pendant que les rôdeurs les abattent.",
              "Les tours orques s'effondrent. La forêt reprend ses droits.",
              [dict(t='destroy', kind='tower'), dict(t='destroy', kind='barracks')],
              dict(res=(600, 400), blds=[('barracks', 160, 70), ('forge', 30, 200), ('sanctum', 250, 40)],
                   units=[('archer', 5), ('soldier', 3), ('heavy', 2), ('healer', 1)],
                   e_blds=[('tower', -190, 90), ('tower', -80, 210), ('tower', -230, -30)]),
              limit=1020, ai=dict(grace=220)),
            M('Le cœur de la Horde', 'horde', 2, 307,
              "Il faut en finir : détruisez la Forteresse de Gorak, au cœur des terres brûlées. "
              "Gardez vos archers derrière vos gardes-lames, soignez avec les druides, et déclenchez le Souffle de la forêt "
              "quand la bataille tourne mal.",
              "La forteresse s'écroule et la forêt respire. Elenwë est libre !",
              [dict(t='hq')],
              dict(res=(700, 500), blds=[('barracks', 160, 70), ('forge', 30, 200), ('temple', 250, 40)],
                   units=[('archer', 5), ('soldier', 3), ('knight', 2), ('healer', 2), ('heavy', 1)], e_res=(500, 300),
                   e_units=[('soldier', 5), ('heavy', 2)], e_blds=[('tower', -190, 90), ('tower', -80, 210), ('tower', -230, -30)]),
              ai=dict(grace=240)),
        ]),
}

OBJ_LABELS = dict(hq='Détruire la base ennemie', survive='Survivre', army='Réunir une armée', unit='Entraîner des unités', gather='Récolter des ressources',
                  kills='Éliminer des ennemis', bld='Construire des bâtiments', techs='Rechercher des technologies', destroy='Détruire des bâtiments ennemis')


def objectives_preview(fac, idx):
    m = CAMPAIGNS[fac]['missions'][idx]
    if m.get('tutorial'):
        return ['Formation guidée en %d étapes' % len(m['setup']['mission']['steps'])]
    out = []
    names = T(fac)
    foe = T(m['enemy'])
    for o in m['setup']['mission']['obj']:
        t = o['t']
        if t == 'hq':
            out.append('Détruire la base ennemie (%s)' % foe['hq'].lower())
        elif t == 'survive':
            out.append('Survivre %d minutes' % (o['n'] // 60))
        elif t == 'army':
            out.append('Réunir %d %s' % (o['n'], (names[o['kind']].lower() + 's') if o.get('kind') else 'combattants'))
        elif t == 'unit':
            out.append('Avoir %d %ss' % (o['n'], names[o['kind']].lower()))
        elif t == 'gather':
            out.append('Récolter %d ressources' % o['n'])
        elif t == 'kills':
            out.append('Éliminer %d ennemis' % o['n'])
        elif t == 'bld':
            out.append('Construire : %s' % names[o['kind']].lower())
        elif t == 'techs':
            out.append('Rechercher %d technologies' % o['n'])
        elif t == 'destroy':
            out.append('Détruire tous les bâtiments : %s' % foe[o['kind']].lower())
    lim = m['setup']['mission'].get('limit')
    if lim:
        out.append('Avant %d minutes' % (lim // 60))
    return out


def mission_setup(fac, idx):
    return copy.deepcopy(CAMPAIGNS[fac]['missions'][idx]['setup'])


def load(path):
    try:
        with open(path) as f:
            return set(json.load(f).get('done', []))
    except Exception:
        return set()


def save(path, done):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'done': sorted(done)}, f)
    except Exception:
        pass


def unlocked(done, fac, idx):
    return idx == 0 or ('%s:%d' % (fac, idx - 1)) in done


def count_done(done, fac):
    return sum(1 for i in range(NMISSIONS) if ('%s:%d' % (fac, i)) in done)
