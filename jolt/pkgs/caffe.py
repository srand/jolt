from jolt import attributes, Parameter
from jolt.pkgs import boost, cmake, hdf5, gflags, glog, protobuf
from jolt.plugins import git, cmake
from jolt.tasks import TaskRegistry


@attributes.requires("requires_boost")
@attributes.requires("requires_cmake")
@attributes.requires("requires_git")
@attributes.requires("requires_hdf5")
@attributes.requires("requires_gflags")
@attributes.requires("requires_glog")
@attributes.requires("requires_protobuf")
class Caffe(cmake.CMake):
    name = "caffe"
    version = Parameter("1.0", help="caffe version.")
    requires_boost = ["boost:version=1.88.0"]
    requires_cmake = ["cmake"]
    requires_git = ["git:url=https://github.com/BVLC/caffe.git,rev={version}"]
    requires_gflags = ["gflags"]
    requires_glog = ["glog"]
    requires_hdf5 = ["hdf5=hdf5:version=hdf5-1.14.6"]
    requires_protobuf = ["protobuf"]
    srcdir = "{git[caffe]}"
    options = [
        "CMAKE_POLICY_VERSION_MINIMUM=3.5",
        # "Protobuf_INCLUDE_DIR={deps[protobuf].path}/include",
        # "Protobuf_LIBRARIES={deps[protobuf].path}/lib/libprotobuf.so",
        # "GFLAGS_INCLUDE_DIR={deps[gflags].path}/include",
        # "GFLAGS_LIBRARY={deps[gflags].path}/lib/libgflags.so",
        # "GLOG_INCLUDE_DIR={deps[glog].path}/include",
        # "GLOG_LIBRARY={deps[glog].path}/lib/libglog.so",
        # "HDF5_INCLUDE_DIRS={deps[hdf5].path}/include",
        # "HDF5_LIBRARIES={deps[hdf5].path}/lib/libhdf5.so",
    ]


# Not yet working
# TaskRegistry.get().add_task_class(Caffe)
