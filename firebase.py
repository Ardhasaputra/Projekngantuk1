import firebase_admin

# Baca file kredensial JSON
cred = firebase_admin.credentials.Certificate('credentials.json')

# Inisialisasi Firebase Admin SDK
firebase_admin.initialize_app(cred)