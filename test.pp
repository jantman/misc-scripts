# == Define: foo::bar::baz
#
# This defined type wraps a nagios_service resource and sets appropriate
# default values for it.
#
# === Parameters:
#
# [*check_command_name*]
#   (string) the name of the check command to use; this should match the
#   name of a
#
# [*check_command_args*]
#   (array of strings) optional list of arguments to pass to the check command,
#   available as $ARG1$ through $ARGn$ in the command's command_line. These
#   arguments are passed to the check_command in Nagios separated by the '!'
#   character, so that should not be used in the arguments.
#
# [*check_use_nrpe*]
#   (boolean) Whether or not this check uses NRPE. If set to true, the check_command
#   will be altered as required to have it executed on the remote host (the node that
#   actually creates this resource) via NRPE. If set to false (default) the command
#   will run on whatever monitoring host the Icinga configuration is collected on.
#
# @TODO: document the rest of the parameters here
#
# === Notes:
#
# For reference on the Puppet nagios_* types, see: http://docs.puppetlabs.com/references/latest/type.html#nagiosservice
#
# For reference on the Icinga objects they create, see: http://docs.icinga.org/latest/en/objectdefinitions.html#objectdefinitions-service
#
# === Authors:
#
# Jason Antman <jason@jasonantman.com>
#
define foo::bar::baz (
  # Nagios/Icinga required params
  $service_description,
  $check_command,
  $check_command_args           = undef,
  $check_use_nrpe               = false,
  $host_name                    = $::fqdn,
  $check_interval               = '5',
  # End Nagios/Icinga required params
  $action_url                   = undef,
  $stalking_options             = $blam::foo::bar,
  $target                       = "foo${bar} baz",
  $use                          = undef
  ) {
  require mymodule::params


}
