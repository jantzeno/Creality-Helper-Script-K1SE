#!/bin/sh

set -e

function customize_menu_ui_k1() {
  top_line
  title '[ CUSTOMIZE MENU ]' "${yellow}"
  inner_line
  hr
  menu_option '1' 'Install' 'Custom Boot Display'
  menu_option '2' 'Remove' 'Custom Boot Display'
  hr
  menu_option '3' 'Remove' 'Creality Web Interface'
  menu_option '4' 'Restore' 'Creality Web Interface'
  hr
  inner_line
  hr
  bottom_menu_option 'b' 'Back to [Main Menu]' "${yellow}"
  bottom_menu_option 'q' 'Exit' "${darkred}"
  hr
  version_line "$(get_script_version)"
  bottom_line
}

function customize_menu_k1() {
  clear
  customize_menu_ui_k1
  local customize_menu_opt
  while true; do
    read -p " ${white}Type your choice and validate with Enter: ${yellow}" customize_menu_opt
    case "${customize_menu_opt}" in
      1)
        if [ -f "$BOOT_DISPLAY_FILE" ]; then
          error_msg "Custom Boot Display is already installed!"
        elif [ ! -d "$BOOT_DISPLAY_FOLDER" ]; then
          error_msg "Please use latest firmware to install Custom Boot Display!"  
        else
          run "install_custom_boot_display" "customize_menu_ui_k1"
        fi;;
      2)
        if [ ! -f "$BOOT_DISPLAY_FILE" ]; then
          error_msg "Custom Boot Display is not installed!"
        elif [ ! -d "$BOOT_DISPLAY_FOLDER" ]; then
          error_msg "Please use latest firmware to restore Stock Boot Display!"  
        else
          run "remove_custom_boot_display" "customize_menu_ui_k1"
        fi;;
      3)
        if [ ! -d "$MAINSAIL_FOLDER" ]; then
          error_msg "Mainsail is needed, please install it first!"
        elif [ ! -f "$CREALITY_WEB_FILE" ]; then
          error_msg "Creality Web Interface is already removed!"
        else
          run "remove_creality_web_interface" "customize_menu_ui_k1"
        fi;;
      4)
        if [ -f "$CREALITY_WEB_FILE" ]; then
          error_msg "Creality Web Interface is already present!"
        elif [ ! -f "$INITD_FOLDER"/S99start_app ]; then
          error_msg "Restore the stock startup service before restoring Creality Web Interface!"
        else
          run "restore_creality_web_interface" "customize_menu_ui_k1"
        fi;;
      B|b)
        clear; main_menu; break;;
      Q|q)
         clear; exit 0;;
      *)
        error_msg "Please select a correct choice!";;
    esac
  done
  customize_menu_k1
}
