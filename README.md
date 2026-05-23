# CodemosModern Themes Registry

This is a personal (for now) auxiliary theme registry for the [Codemos Modern][codemos-modern] theme suite.

### 🔗 Compatibility

The table below showcases the compatibility between different distributions of this registry and their respective supported distributions of [Codemos Modern][codemos-modern].

| Registry Distribution  | Supported CM Distribution |
| ---------------------- | ------------------------- |
| v1.0.0...latest        | v3.1.1...latest           |

### 🎯 Target

To integrate [vscodethemes.com][vscodethemes.com]'s collection of VSCode themes for use in [Codemos Modern][codemos-modern]!

### ❤️ Subscription

Add the following entry to your `settings.json` file.

```jsonc
{ // settings.json
  "codemosModern.auxiliaryThemeRegistries": [
    // ...
    "AvinashReddy3108/CodemosModern-Themes-Registry",
    // ...
  ]
}
```

### 🎨 Catalog

You can search and preview the themes over on [vscodethemes.com][vscodethemes.com].

Individual publishers & themes are listed in the `index.json` file at the root of this repository. You can find the list of themes in the `themes` property of the `index.json` file. Each theme is represented by an object with the following properties.

- **Publisher:** The publisher of the theme.
- **Extension:** The name of the extension containing the themes.
- **Theme:** The name of the theme.
- **Origin:** The origin of the theme.
- **License:** The license of the theme.

### 📋 Change Log

    <Not much to look here at the moment>

### 🙌🏼 Contribution

    <WIP, any and all contrubutions are welcome!>

<!-- References -->
[codemos-modern]: https://github.com/EmrecanKaracayir/Codemos-Modern
[vscodethemes.com]: https://vscodethemes.com
