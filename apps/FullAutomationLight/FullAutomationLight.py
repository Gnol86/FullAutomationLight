"""
FullAutomationLight - Automated Light Control for Home Assistant
==================================================================

This module provides automated light control functionality for Home Assistant,
integrating with various sensors and conditions to optimize light management.

Features:
---------
- Automatic light control based on room occupancy
- Natural lighting adaptation based on sun elevation
- Scene-based lighting control
- Luminance-based light management
- Configurable transitions between states

Requirements:
------------
- Home Assistant with AppDaemon
- Light entities
- Optional: occupancy sensors, luminance sensors, sun entity

Configuration:
-------------
Example configuration in apps.yaml:
```yaml
light_automation:
  module: FullAutomationLight
  class: FullAutomationLight
  debug: false
  rooms:
    living_room:
      lights_entity: light.living_room
      occupancy_entity: binary_sensor.living_room_occupancy
      luminance_entity: sensor.living_room_luminance
      luminance_limit: 10
      occupancy_off_delay: 300
  natural_lighting:
    modes:
      - name: default
        max_brightness: 255
        min_brightness: 100
        max_kelvin: 5500
        min_kelvin: 2000
```

Technical Details:
-----------------
The app uses several key components:
1. Room Management: Handles individual room configurations and states
2. Natural Lighting: Adjusts light temperature and brightness based on sun position
3. Scene Control: Manages predefined lighting scenes
4. State Transitions: Configurable transition times between states

Error Handling:
--------------
- All entity interactions are wrapped in try-except blocks
- Invalid configurations are logged with detailed error messages
- Missing entities are gracefully handled with fallback values
- Temperature conversion errors are caught and logged

Author: @gnol86
License: MIT
Repository: https://github.com/Gnol86/FullAutomationLight
"""

import appdaemon.plugins.hass.hassapi as hass # type: ignore

class FullAutomationLight(hass.Hass):
    """
    Main class for handling automated light control in Home Assistant.
    Inherits from AppDaemon's Hass class.
    """

    def initialize(self):
        """
        Initialize the automation system.
        Sets up initial configuration, loads room settings,
        and establishes event listeners.
        """
        self.debug = self.args['debug'] if 'debug' in self.args else False
        self.log("#-------------------------#")
        self.log("|  Full Automation Light  |")
        self.log("#-------------------------#")
        self.log("")

        # init
        self.entities = []
        self.natural_lighting = self.init_natural_lighting()
        self.transitions = self.init_transitions()
        self.rooms = self.init_rooms()

        # set all lights
        for room_name in self.rooms:
            self.set_is_light_on(room_name, "init")
        self.log("Initialized")

    def add_entity(self, entity):
        """
        Add an entity to the tracking list if not already present.
        
        Args:
            entity (str): The entity_id to add to tracking
        """
        if not entity in self.entities:
            self.entities.append(entity)

    def set_light(self, room_name, trigger):
        """
        Control light state based on room settings and trigger type.
        
        Args:
            room_name (str): Name of the room to control
            trigger (str): Event that triggered the light change 
                         ('occupancy', 'scene', 'natural_lighting', etc.)
        """
        transition = self.transitions.get(trigger, 1)
        self.debug_log("{}: {} ({})".format(room_name, trigger, transition))

        room = self.rooms[room_name]
        mode = ""

        if room['is_light_on']:
            if 'scenes' in room:
                for scene in room['scenes']:
                    if self.get_state(scene['scene_trigger_entity']) == scene['scene_trigger_value']:
                        mode = "scene"
                        entity = self.get_entity(scene['scene_entity'])
                        domain = scene['scene_entity'].split('.')[0]
                        if domain == "script" or transition == None:
                            entity.call_service("turn_on")
                        else:
                            entity.call_service(
                                "turn_on", transition=transition)
                        self.debug_log(
                            "ON - Scene : {}".format(scene['scene_entity']))
                        break
            if mode == "" and self.natural_lighting and 'natural_lighting' in room:
                for natural_lighting in room['natural_lighting']:
                    mode = 'natural_lighting'
                    brightness = self.natural_lighting['modes'][natural_lighting['name']]['brightness']
                    kelvin = self.natural_lighting['modes'][natural_lighting['name']]['kelvin']
                    entity = self.get_entity(
                        natural_lighting['lights_entity']) if 'lights_entity' in natural_lighting else self.get_entity(room['lights_entity'])
                    if natural_lighting['boost_brightness_pct'] != 0:
                        brightness = int(
                            brightness + (brightness / 100 * natural_lighting['boost_brightness_pct']))
                        brightness = 255 if brightness > 255 else brightness
                        brightness = 1 if brightness < 1 else brightness
                    if transition == None:
                        entity.call_service(
                            "turn_on", brightness=brightness, kelvin=kelvin)
                    else:
                        entity.call_service(
                            "turn_on", brightness=brightness, kelvin=kelvin, transition=transition)
                self.debug_log("ON - Natural lighting")
            if mode == "":
                entity = self.get_entity(room['lights_entity'])
                if transition == None:
                    entity.call_service("turn_on")
                else:
                    entity.call_service("turn_on", transition=transition)
                self.debug_log("ON")
        else:
            self.debug_log("OFF")
            entity = self.get_entity(room['lights_entity'])
            if self.transitions['off'] == None:
                entity.call_service("turn_off")
            else:
                entity.call_service(
                    "turn_off", transition=self.transitions['off'])
        self.debug_log("")

    def init_rooms(self):
        """
        Initialize room configurations from the apps.yaml settings.
        Sets up default values and validates room configurations.
        
        Returns:
            dict: Dictionary of room configurations
        """
        self.debug_log("Init Rooms...")
        default_room = {
            "occupancy_entity": False,
            "lights_entity": False,
            "occupancy_off_delay": 0,
            "luminance_entity": False,
            "luminance_limit": 10,
            "luminance_hysteresis": 0,
            "hight_luminance_off_light": False,
            "occupancy": True,
            "low_light": True,
            "is_light_on": False
        }
        default_natural_lighting = {
            "name": "default",
            "boost_brightness_pct": 0
        }
        rooms = {}
        if 'rooms' in self.args:
            for name in self.args['rooms']:
                rooms[name] = default_room.copy()
                rooms[name].update({k: v for k, v in self.args['rooms'][name].items(
                ) if k not in ['natural_lighting', 'scenes']})
                if not rooms[name]['lights_entity'] or not self.get_entity(rooms[name]['lights_entity']).exists():
                    self.log(f"'{name}' : 'lights_entity' not exists !!!")
                    del rooms[name]
                    continue
                self.add_entity(rooms[name]['lights_entity'])

                if 'natural_lighting' in self.args['rooms'][name]:
                    rooms[name]['natural_lighting'] = []
                    if type(self.args['rooms'][name]['natural_lighting']) == list:
                        nb = 0
                        for natural_lighting in self.args['rooms'][name]['natural_lighting']:
                            rooms[name]['natural_lighting'].append(
                                default_natural_lighting.copy())
                            rooms[name]['natural_lighting'][nb].update(
                                {k: v for k, v in natural_lighting.items()})
                            if not rooms[name]['natural_lighting'][nb]['name'] in self.natural_lighting['modes']:
                                rooms[name]['natural_lighting'][nb]['name'] = 'default'
                            if 'natural_entity' in rooms[name]['natural_lighting'][nb]:
                                self.add_entity(
                                    rooms[name]['natural_lighting'][nb]['natural_entity'])
                            else:
                                rooms[name]['natural_lighting'][nb]['natural_entity'] = rooms[name]['lights_entity']

                            nb += 1
                    else:
                        rooms[name]['natural_lighting'].append(
                            default_natural_lighting.copy())
                        rooms[name]['natural_lighting'][0]['natural_entity'] = rooms[name]['lights_entity']

                if 'scenes' in self.args['rooms'][name] and type(self.args['rooms'][name]['scenes']) == list:
                    rooms[name]['scenes'] = self.args['rooms'][name]['scenes']
                    for scene in rooms[name]['scenes']:
                        if ('scene_entity' in scene
                                and self.get_entity(scene['scene_entity']).exists()
                                and 'scene_trigger_entity' in scene
                                and self.get_entity(scene['scene_trigger_entity']).exists()
                                and 'scene_trigger_value' in scene
                                and (scene['scene_entity'].split('.')[0] == "script" or scene['scene_entity'].split('.')[0] == "scene")
                            ):
                            self.listen_state(
                                self.callback_room, scene['scene_trigger_entity'], new=scene['scene_trigger_value'], room_name=name, trigger="scene")
                            self.listen_state(
                                self.callback_room, scene['scene_trigger_entity'], old=scene['scene_trigger_value'], room_name=name, trigger="scene")

                if rooms[name]['occupancy_entity'] and self.get_entity(rooms[name]['occupancy_entity']).exists():
                    if rooms[name]['occupancy_off_delay'] > 0:
                        self.listen_state(
                            self.callback_room, rooms[name]['occupancy_entity'], new="on", room_name=name, trigger="occupancy")
                        self.listen_state(self.callback_room, rooms[name]['occupancy_entity'], new="off",
                                          duration=rooms[name]['occupancy_off_delay'], room_name=name, trigger="occupancy")
                    else:
                        self.listen_state(
                            self.callback_room, rooms[name]['occupancy_entity'], room_name=name, trigger="occupancy")
                if rooms[name]['luminance_entity'] and self.get_entity(rooms[name]['luminance_entity']).exists():
                    self.listen_state(
                        self.callback_room, rooms[name]['luminance_entity'], room_name=name, trigger="low_light")

        self.debug_log(rooms)
        self.debug_log("Rooms Initialized")
        self.debug_log("")
        return rooms

    def callback_room(self, entity, attribute, old, new, kwargs):
        """
        Callback handler for room state changes (occupancy/luminance).
        
        Args:
            entity (str): Entity that triggered the callback
            attribute (str): Changed attribute
            old (str): Previous state value
            new (str): New state value
            kwargs (dict): Additional callback arguments
        """
        self.set_is_light_on(kwargs['room_name'], kwargs['trigger'])

    def set_is_light_on(self, room_name, trigger):
        """
        Determine if a room's lights should be on based on conditions.
        
        Args:
            room_name (str): Name of the room to evaluate
            trigger (str): Event that triggered the evaluation
        """
        if self.rooms[room_name]['occupancy_entity']:
            self.rooms[room_name]['occupancy'] = True if self.get_state(
                self.rooms[room_name]['occupancy_entity']) in ["on", "home", True, "true", "True"] else False

        if self.rooms[room_name]['luminance_entity']:
            luminance_limit = self.int(
                self.rooms[room_name]['luminance_limit'])
            if self.rooms[room_name]['low_light']:
                luminance_limit += self.int(
                    self.rooms[room_name]['luminance_hysteresis'])
            else:
                luminance_limit -= self.int(
                    self.rooms[room_name]['luminance_hysteresis'])
            self.rooms[room_name]['low_light'] = True if self.int(self.get_state(
                self.rooms[room_name]['luminance_entity'])) <= luminance_limit else False

        old_is_light_on = self.rooms[room_name]['is_light_on']
        
        # Vérifier si une scène avec force_light_on est active
        force_light_on = False
        if 'scenes' in self.rooms[room_name]:
            for scene in self.rooms[room_name]['scenes']:
                if (self.get_state(scene['scene_trigger_entity']) == scene['scene_trigger_value'] and
                    'scene_force_light_on' in scene and scene['scene_force_light_on']):
                    force_light_on = True
                    break
        
        if force_light_on:
            self.rooms[room_name]['is_light_on'] = True
        elif not (self.rooms[room_name]['is_light_on'] and not self.rooms[room_name]['low_light']) or self.rooms[room_name]['hight_luminance_off_light'] or trigger == 'occupancy':
            self.rooms[room_name]['is_light_on'] = self.rooms[room_name]['occupancy'] and self.rooms[room_name]['low_light']

        if trigger in ["init", "scene", "natural_lighting"] or old_is_light_on != self.rooms[room_name]['is_light_on']:
            # Si force_light_on est actif et que les lumières étaient éteintes, on utilise la transition occupancy
            if force_light_on and trigger == "scene" and not old_is_light_on:
                self.set_light(room_name, "occupancy")
            else:
                self.set_light(room_name, trigger)

    def init_transitions(self):
        """
        Initialize transition time settings for different state changes.
        
        Returns:
            dict: Dictionary of transition settings
        """
        transitions = {
            'init': None,
            'occupancy': None,
            'low_light': 15,
            'scene': 10,
            'natural_lighting': 10,
            'off': None
        }

        # Update transitions dictionary with provided values from args
        transitions.update(self.args.get('transitions', {}))

        self.debug_log("Transitions Initialized")
        self.debug_log("")

        return transitions

    def init_natural_lighting(self):
        """
        Initialize natural lighting settings and sun tracking.
        Sets up sun elevation monitoring and lighting adjustments.
        
        Returns:
            dict|bool: Natural lighting configuration or False if disabled
        """
        # Default values for natural lighting
        natural_lighting = {
            'modes': {
                'default': {
                    'max_brightness': 255,
                    'min_brightness': 100,
                    'max_kelvin': 5500,
                    'min_kelvin': 2000,
                    'brightness': 0,
                    'kelvin': 0,
                }
            },
            'sun_entity': 'sun.sun',
            'min_elevation_for_brightness': -20,
            'max_elevation_for_brightness': 20,
            'min_elevation_for_kelvin': 0,
            'max_elevation_for_kelvin': 20
        }

        # Check if natural_lighting exists in self.args
        if 'natural_lighting' not in self.args:
            self.debug_log("Natural Lighting Inactive")
            self.debug_log("")
            return False

        self.debug_log("Init Natural Lighting...")

        # Get natural lighting arguments from self.args
        nl_args = self.args['natural_lighting']

        # Check if modes exist in natural lighting arguments
        if 'modes' in nl_args:
            modes = nl_args['modes']
            # Check if modes is a list
            if type(modes) == list:
                # Loop through modes and update the default values
                for mode in modes:
                    natural_lighting['modes'][mode['name']
                                              ] = natural_lighting['modes']['default'].copy()
                    natural_lighting['modes'][mode['name']].update({k: v for k, v in mode.items(
                    ) if k in ['max_brightness', 'min_brightness', 'max_kelvin', 'min_kelvin']})

        # Get sun entity from natural lighting arguments
        sun_entity = nl_args.get('sun_entity', 'sun.sun')
        self.add_entity(sun_entity)

        # Update natural lighting with values from natural lighting arguments
        natural_lighting.update({k: v for k, v in nl_args.items() if k in [
                                'min_elevation_for_brightness', 'max_elevation_for_brightness', 'min_elevation_for_kelvin', 'max_elevation_for_kelvin']})

        # Get sun elevation state
        natural_lighting['sun_elevation'] = self.int(
            self.get_state(sun_entity, attribute='elevation'))

        # Listen to changes in sun elevation state
        self.listen_state(self.callback_sun_elevation,
                          sun_entity, attribute='elevation')
        self.debug_log(f"Listen state of {sun_entity}")

        # Set natural lighting
        natural_lighting = self.set_natural_lighting(natural_lighting)

        self.debug_log(natural_lighting)
        self.debug_log("Natural Lighting Initialized")
        self.debug_log("")
        return natural_lighting

    def callback_sun_elevation(self, entity, attribute, old, new, kwargs):
        """
        Handle changes in sun elevation to adjust natural lighting.
        
        Args:
            entity (str): Sun entity
            attribute (str): Changed attribute (elevation)
            old (str): Previous elevation value
            new (str): New elevation value
            kwargs (dict): Additional callback arguments
        """
        self.natural_lighting['sun_elevation'] = self.int(new)
        self.natural_lighting = self.set_natural_lighting(
            self.natural_lighting)
        for room_name in self.rooms:
            if 'natural_lighting' in self.rooms[room_name] and self.rooms[room_name]['natural_lighting'] and self.rooms[room_name]['is_light_on']:
                self.set_light(room_name, "natural_lighting")

    def set_natural_lighting(self, natural_lighting):
        """
        Calculate brightness and color temperature based on sun elevation.
        
        Args:
            natural_lighting (dict): Natural lighting configuration
            
        Returns:
            dict: Updated natural lighting settings
        """
        self.debug_log("---")
        self.debug_log(f"Sun elevation: {natural_lighting['sun_elevation']}")
        for name in natural_lighting['modes']:
            mode = natural_lighting['modes'][name]
            # Calculate the brightness value based on the sun elevation
            mode['brightness'] = self.scale(
                natural_lighting['sun_elevation'],
                (natural_lighting['min_elevation_for_brightness'],
                 natural_lighting['max_elevation_for_brightness']),
                (mode['min_brightness'], mode['max_brightness'])
            )
            # Calculate the kelvin value based on the sun elevation
            mode['kelvin'] = self.scale(
                natural_lighting['sun_elevation'],
                (natural_lighting['min_elevation_for_kelvin'],
                 natural_lighting['max_elevation_for_kelvin']),
                (mode['min_kelvin'], mode['max_kelvin'])
            )
            self.debug_log(
                f"{name} - brightness: {mode['brightness']} - kelvin: {mode['kelvin']}")
        self.debug_log("---")
        return natural_lighting

    def scale(self, val, src, dst):
        """
        Scale a value from one range to another.
        
        Args:
            val (float): Value to scale
            src (tuple): Source range (min, max)
            dst (tuple): Destination range (min, max)
            
        Returns:
            int: Scaled value
        """
        return self.int((min(max(val, src[0]), src[1]) - src[0]) / (src[1]-src[0]) * (dst[1]-dst[0]) + dst[0])

    def int(self, val):
        """
        Safely convert a value to integer.
        
        Args:
            val (str|float): Value to convert
            
        Returns:
            int: Converted value, 0 if conversion fails
        """
        if val in ['unknown', 'unavailable']:
            return 0
        try:
            return int(float(val))
        except:
            return val

    def debug_log(self, message):
        """
        Log debug messages if debug mode is enabled.
        
        Args:
            message (str): Message to log
        """
        if self.debug:
            self.log(message)
