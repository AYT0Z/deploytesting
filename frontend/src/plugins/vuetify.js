import 'vuetify/styles'
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'dark',
    themes: {
      dark: {
        colors: {
          primary: '#7c4dff',
          secondary: '#00e5ff',
          surface: '#12121a',
        },
      },
    },
  },
})
