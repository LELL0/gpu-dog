import Gio from 'gi://Gio'
import { LOG_PREFIX, characterSpriteDirs } from './constants.js'


export const getSpritesPack = (root, character = 'cat') => {
	const dir = characterSpriteDirs[character] ?? characterSpriteDirs.cat

	const loadState = (state) => {
		const sprites = []
		let i = 0

		while (true) {
			const path = `${root}/resources/icons/${dir}/${state}/sprite-${i}-symbolic.svg`

			if (!Gio.file_new_for_path(path).query_exists(null)) {
				break
			}

			sprites.push(Gio.icon_new_for_string(path))
			i++
		}

		if (sprites.length === 0) {
			console.error(`${LOG_PREFIX}: no sprites found for "${dir}/${state}"`)
		}


		return sprites
	}

	return {
		active: loadState('active'),
		idle: loadState('idle'),
	}
}

const formatter = new Intl.NumberFormat(undefined, {
	maximumFractionDigits: 0,
	style: 'percent',
})

export const formatNumber = value => formatter.format(value)

// Brand colors by PCI vendor id, most preferred first: on hybrid systems the
// discrete GPU's brand wins over the integrated one.
const VENDOR_COLORS = [
	['0x10de', '#76b900'], // NVIDIA green
	['0x1002', '#ed1c24'], // AMD red
	['0x8086', '#0071c5'], // Intel blue
]
export const FALLBACK_COLOR = '#76b900'

let detectedColor = null

// Color used while the `color` setting is empty (auto). Reads only the PCI
// vendor id from sysfs, which never wakes a runtime-suspended GPU.
export const getAutoColor = () => {
	if (detectedColor !== null)
		return detectedColor

	const vendors = new Set()
	try {
		const en = Gio.File.new_for_path('/sys/class/drm').enumerate_children('standard::name', Gio.FileQueryInfoFlags.NONE, null)
		let info
		while ((info = en.next_file(null)) !== null) {
			const name = info.get_name()
			if (!/^card\d+$/.test(name))
				continue
			try {
				const [, bytes] = Gio.File.new_for_path(`/sys/class/drm/${name}/device/vendor`).load_contents(null)
				vendors.add(new TextDecoder().decode(bytes).trim().toLowerCase())
			} catch {
				// card without a PCI vendor file
			}
		}
		en.close(null)
	} catch (e) {
		console.error(`${LOG_PREFIX}: GPU vendor detection failed: ${e}`)
	}

	detectedColor = VENDOR_COLORS.find(([id]) => vendors.has(id))?.[1] ?? FALLBACK_COLOR
	return detectedColor
}

export const resolveColor = setting => setting.replace(/[;{}]/g, '').trim() || getAutoColor()
