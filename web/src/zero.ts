import { Zero } from '@rocicorp/zero'
import { schema } from './schema'

const ZERO_SERVER = import.meta.env.VITE_ZERO_URL || 'http://localhost:4848'

export const zero = new Zero({
  userID: 'anon',
  server: ZERO_SERVER,
  schema,
})
