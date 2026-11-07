from jolt import attributes, BooleanParameter, Parameter
from jolt.pkgs import compiler, protobuf
from jolt.plugins import cmake, cxxinfo, git
from jolt.tasks import TaskRegistry


@attributes.requires("requires_git")
@attributes.requires("requires_protobuf")
@cmake.requires()
@cmake.use_ninja()
@cxxinfo.publish(libraries=["protobuf-c"])
@attributes.requires("requires_compiler")
class ProtobufC(cmake.CMake):
    """ Protocol Buffers for C: the runtime library and the protoc-gen-c plugin """

    name = "protobuf-c"
    version = Parameter("1.5.2", help="protobuf-c version.")
    pic = BooleanParameter(False, help="Build with position independent code.")
    shared = BooleanParameter(False, help="Build shared libraries.")
    requires_compiler = ["virtual/compiler/c", "virtual/compiler/cxx"]
    requires_git = ["git:clean=true,url=https://github.com/protobuf-c/protobuf-c.git,rev=v{version}"]
    # The plugin links with the protoc library
    requires_protobuf = ["protobuf"]
    srcdir = "{git[protobuf-c]}/build-cmake"
    options = [
        "BUILD_SHARED_LIBS={shared[ON,OFF]}",
        "BUILD_TESTS=OFF",
        "CMAKE_POSITION_INDEPENDENT_CODE={pic[ON,OFF]}",
    ]

    def run(self, deps, tools):
        # Protobuf 33 removed FieldDescriptor::label(). Derive the label from
        # the predicates that remain instead. The searches don't include line
        # endings, which are CRLF in checkouts on Windows.
        with tools.cwd(self.srcdir, "..", "protoc-gen-c"):
            tools.replace_in_file(
                "compat.h",
                "namespace compat {{",
                "namespace compat {{\n\n"
                "inline google::protobuf::FieldDescriptor::Label GetLabel(const google::protobuf::FieldDescriptor *field) {{\n"
                "  if (field->is_repeated()) return google::protobuf::FieldDescriptor::LABEL_REPEATED;\n"
                "  if (field->is_required()) return google::protobuf::FieldDescriptor::LABEL_REQUIRED;\n"
                "  return google::protobuf::FieldDescriptor::LABEL_OPTIONAL;\n"
                "}}\n")
            tools.replace_in_file("compat.h", "\nnamespace protobuf_c {{", "\n#include <google/protobuf/descriptor.h>\n\nnamespace protobuf_c {{")
            for source in tools.glob("c_*field.cc"):
                tools.replace_in_file(source, "descriptor_->label()", "compat::GetLabel(descriptor_)")
        super().run(deps, tools)

    def publish(self, artifact, tools):
        super().publish(artifact, tools)
        artifact.environ.PATH.append("bin")
        if self.shared:
            artifact.environ.LD_LIBRARY_PATH.append("lib")


TaskRegistry.get().add_task_class(ProtobufC)
