#include <iostream>
#include "simple.h"

extern int add(int, int);
extern int sub(int, int);

int main() {
    std::cout << add(13, 37) << "\n";
    std::cout << "Hello world!\n";
    std::cout << get_name() << "\n";

    return 0;
}