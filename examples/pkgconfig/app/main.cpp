#include "lib.hpp"

#include <cstdlib>
#include <iostream>
#include <string>

int main() {
    std::string message = lib_function();
    std::cout << message << std::endl;
    return EXIT_SUCCESS;
}
