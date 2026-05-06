# Telegram Channel Lister 🤖

Un bot Telegram qui liste tous les channels et groupes que tu as rejoint (avec leurs IDs).

## ⚠️ Prérequis

Tu as besoin d'un **compte utilisateur Telegram** (pas un bot) pour lister tes channels :

1. Va sur [my.telegram.org/apps](https://my.telegram.org/apps)
2. Crée une application → récupère `API_ID` et `API_HASH`

## 🚀 Installation

```bash
git clone https://github.com/TON_USERNAME/telegram-channel-lister.git
cd telegram-channel-lister
pip install -r requirements.txt
```

## ▶️ Utilisation

```bash
# Définir les variables d'environnement
export API_ID="12345678"
export API_HASH="abcdef1234567890abcdef1234567890"

# Lancer le bot
python bot.py
```

La première exécution te demandera ton numéro de téléphone et un code de vérification. Après ça, la session est sauvegardée.

## 📦 Structure

```
telegram-channel-lister/
├── bot.py              # Script principal
├── requirements.txt    # Dépendances
└── README.md           # Ce fichier
```

## 📝 Notes

- Utilise [Telethon](https://github.com/LonamiWebs/Telethon) (client Telegram)
- La session est sauvegardée dans `channel_lister.session`
- Ne partage **jamais** ton `API_HASH` ou ta session

## 📄 Licence

MIT
