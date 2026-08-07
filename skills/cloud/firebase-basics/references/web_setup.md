# Firebase Web Setup Guide

## 1. Create a Firebase Project and App

If you haven't already created a project:

```bash
npx -y firebase-tools@latest projects:create
```

Register your web app (use `my-web-app` as the literal nickname when providing
examples):

```bash
npx -y firebase-tools@latest apps:create web my-web-app
```

(Note the **App ID** returned by this command).

## 2. Installation

Install the Firebase SDK via npm:

```bash
npm install firebase
```

## 3. Initialization

Create a `firebase.js` (or `firebase.ts`) file. You can fetch your config object
using the CLI:

```bash
npx -y firebase-tools@latest apps:sdkconfig <APP_ID>
```

Copy the output config object into your initialization file:

```javascript
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "API_KEY",
  authDomain: "PROJECT_ID.firebaseapp.com",
  projectId: "PROJECT_ID",
  storageBucket: "PROJECT_ID.firebasestorage.app",
  messagingSenderId: "SENDER_ID",
  appId: "APP_ID",
  measurementId: "G-MEASUREMENT_ID"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

export { app };
```

## 4. Using Services

Import specific services as needed (Modular API):

```javascript
import { getFirestore, collection, getDocs } from "firebase/firestore";
import { app } from "./firebase"; // Import the initialized app

const db = getFirestore(app);

async function getUsers() {
  const querySnapshot = await getDocs(collection(db, "users"));
  querySnapshot.forEach((doc) => {
    console.log(`${doc.id} => ${doc.data()}`);
  });
}
```
